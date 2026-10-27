"""拟人化表现层：处理消息分句、动态打字延迟、正在输入状态与下发。"""

import asyncio
import logging
import random
import re
from typing import Any, Callable, Coroutine, List
from app.core.database import async_session_factory
from app.models.orm import ChatMessage

logger = logging.getLogger(__name__)

# 匹配并清除各类时间戳前缀 (如 [2026-10-27 22:43:00]、[22:43]、2026-10-27 22:43: 等)
_TIMESTAMP_PATTERN = re.compile(
    r"^(\[|\(|【)\s*(?:\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?(?:\s+|\s*T\s*)?)?\d{1,2}:\d{2}(?::\d{2})?\s*(\]|\)|】)\s*[:：\-—]?\s*|"
    r"^\[\d{4}[-/]\d{1,2}[-/]\d{1,2}\]\s*[:：\-—]?\s*|"
    r"^\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?(?:\s+|\s*T\s*)\d{1,2}:\d{2}(?::\d{2})?\s*[:：\-—]?\s*",
    flags=re.MULTILINE,
)


class HumanizerPipeline:
    """拟人化消息处理管道。"""

    def __init__(self, typing_speed: float = 0.15):
        self.typing_speed = typing_speed

    def clean_text(self, text: str) -> str:
        """清洗回复文本：去除首行时间戳与 Markdown 格式标记。"""
        # 1. 移除时间戳残留
        cleaned = _TIMESTAMP_PATTERN.sub("", text)
        # 2. 移除加粗、斜体符号与代码块标记
        cleaned = re.sub(r"[*_`]", "", cleaned)
        # 3. 移除行首的标题号与列表符
        cleaned = re.sub(r"^[#\->\s]+", "", cleaned, flags=re.MULTILINE)
        return cleaned.strip()

    def split_sentences(self, text: str, max_sentences: int = 3) -> List[str]:
        """按换行符与标点符号智能拆分短句，保证短消息自然下发。"""
        if not text:
            return []

        # 1. 优先按显式换行符切分
        raw_lines = [line.strip() for line in text.split("\n") if line.strip()]
        cleaned_lines = []
        for line in raw_lines:
            cl = self.clean_text(line)
            if cl:
                cleaned_lines.append(cl)

        # 若模型已显式分多行输出，则直接采用
        if len(cleaned_lines) > 1:
            return cleaned_lines[:max_sentences]

        if not cleaned_lines:
            return []

        single = cleaned_lines[0]
        # 若单行简短，无需强行拆分
        if len(single) <= 22:
            return [single]

        # 2. 若模型未换行输出长段落，按句末标点符号智能切分（保留标点）
        tokens = re.split(r"([。！？!?~～]+|……|\.{2,3})", single)
        raw_sentences = []
        current = ""
        for tok in tokens:
            if not tok:
                continue
            current += tok
            if re.match(r"^[。！？!?~～]+|……|\.{2,3}$", tok):
                raw_sentences.append(current.strip())
                current = ""
        if current.strip():
            raw_sentences.append(current.strip())

        # 合并过短碎片，避免过于细碎
        merged = []
        for s in raw_sentences:
            if not s:
                continue
            if merged and len(merged[-1]) + len(s) <= 22 and len(merged) < max_sentences:
                merged[-1] += s
            else:
                merged.append(s)

        # 3. 若切分后依然仅有 1 句且较长，尝试按逗号二次切分
        if len(merged) == 1 and len(merged[0]) > 28:
            comma_tokens = re.split(r"([，,]+)", merged[0])
            sub_sentences = []
            cur = ""
            for tok in comma_tokens:
                cur += tok
                if re.match(r"^[，,]+$", tok):
                    sub_sentences.append(cur.strip())
                    cur = ""
            if cur.strip():
                sub_sentences.append(cur.strip())

            merged_comma = []
            for s in sub_sentences:
                if not s:
                    continue
                if merged_comma and len(merged_comma[-1]) + len(s) <= 22 and len(merged_comma) < max_sentences:
                    merged_comma[-1] += s
                else:
                    merged_comma.append(s)
            if len(merged_comma) > 1:
                merged = merged_comma

        return merged[:max_sentences]

    async def dispatch(
        self,
        user_id: int,
        raw_reply: str,
        send_message_fn: Callable[[int, str], Coroutine[Any, Any, None]],
        set_status_fn: Callable[[int], Coroutine[Any, Any, None]],
    ) -> None:
        """执行拟人化分句发送与打字延时。"""
        sentences = self.split_sentences(raw_reply)
        if not sentences:
            return

        for idx, sentence in enumerate(sentences):
            # 仅在配置打字耗时时向客户端同步输入中状态
            if self.typing_speed > 0:
                try:
                    await set_status_fn(user_id)
                except Exception as e:
                    logger.debug(f"更新正在输入状态异常: {e}")

            # 动态计算打字耗时，零延迟时首句即发，多句分段保留极短间隔防风控
            if self.typing_speed <= 0:
                sleep_duration = 0.0 if idx == 0 else 0.1
            else:
                base_delay = 1.0 if idx == 0 else 0.5
                char_delay = len(sentence) * self.typing_speed
                total_delay = base_delay + char_delay + random.uniform(0.2, 0.6)
                sleep_duration = min(max(total_delay, 0.5), 8.0)

            if sleep_duration > 0:
                await asyncio.sleep(sleep_duration)

            # 发送私聊消息
            await send_message_fn(user_id, sentence)

            # 持久化存储该条回复
            async with async_session_factory() as session:
                msg_record = ChatMessage(
                    user_id=user_id,
                    role="assistant",
                    content=sentence,
                    image_urls=None,
                )
                session.add(msg_record)
                await session.commit()

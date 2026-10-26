"""拟人化表现层：处理消息分句、动态打字延迟、正在输入状态与下发。"""

import asyncio
import logging
import random
import re
from typing import Any, Callable, Coroutine, List
from app.core.database import async_session_factory
from app.models.orm import ChatMessage

logger = logging.getLogger(__name__)


class HumanizerPipeline:
    """拟人化消息处理管道。"""

    def __init__(self, typing_speed: float = 0.15):
        self.typing_speed = typing_speed

    def clean_text(self, text: str) -> str:
        """去除 Markdown 格式符号作为安全兜底。"""
        # 移除加粗、斜体符号与代码块标记
        cleaned = re.sub(r"[*_`]", "", text)
        # 移除行首的标题号与列表符
        cleaned = re.sub(r"^[#\->\s]+", "", cleaned, flags=re.MULTILINE)
        return cleaned.strip()

    def split_sentences(self, text: str) -> List[str]:
        """按换行符拆分短句。"""
        lines = text.split("\n")
        sentences = []
        for line in lines:
            cleaned_line = self.clean_text(line)
            if cleaned_line:
                sentences.append(cleaned_line)
        return sentences

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
            # 发送前设置“正在输入...”状态
            try:
                await set_status_fn(user_id)
            except Exception as e:
                logger.debug(f"更新正在输入状态异常: {e}")

            # 动态计算打字耗时（首句略长以模拟理解）
            base_delay = 1.0 if idx == 0 else 0.5
            char_delay = len(sentence) * self.typing_speed
            total_delay = base_delay + char_delay + random.uniform(0.2, 0.6)

            # 限制单句等待上限，避免对方等待过久
            sleep_duration = min(max(total_delay, 1.0), 8.0)
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

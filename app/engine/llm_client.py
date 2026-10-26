"""大语言模型异步调用客户端，支持图文多模态与时间戳提示词组装。"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from openai import AsyncOpenAI, APIConnectionError, APIStatusError, APITimeoutError
from app.engine.think_stripper import ThinkStripper

logger = logging.getLogger(__name__)


class LLMClient:
    """OpenAI 兼容接口客户端封装。"""

    def __init__(
        self,
        api_base: str,
        api_key: str,
        model: str,
        temperature: float = 0.8,
        top_p: float = 0.9,
        max_tokens: int = 2048,
    ):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key or "sk-no-auth"
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.stripper = ThinkStripper()

        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.api_base,
            timeout=60.0,
        )

    async def generate_response(
        self,
        system_prompt: str,
        history_messages: List[Dict[str, Any]],
        new_user_text: str,
        new_image_urls: Optional[List[str]] = None,
    ) -> str:
        """组装上下文、时间戳与多模态数据并调用大模型。"""
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 构造带有当前实时时间说明的系统提示词
        full_system_prompt = (
            f"{system_prompt}\n\n"
            f"【环境参考】当前系统时间为：{current_time_str}。"
        )

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": full_system_prompt}
        ]

        # 追加历史消息 (带时间戳)
        for msg in history_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            time_str = msg.get("created_at", "")
            images = msg.get("image_urls") or []

            prefix = f"[{time_str}] " if time_str else ""
            formatted_text = f"{prefix}{content}"

            if images and role == "user":
                content_list = [{"type": "text", "text": formatted_text}]
                for img_url in images:
                    content_list.append({"type": "image_url", "image_url": {"url": img_url}})
                messages.append({"role": role, "content": content_list})
            else:
                messages.append({"role": role, "content": formatted_text})

        # 追加本次待回答的用户消息
        latest_text = f"[{current_time_str}] {new_user_text}"
        if new_image_urls:
            latest_content: List[Dict[str, Any]] = [{"type": "text", "text": latest_text}]
            for img_url in new_image_urls:
                latest_content.append({"type": "image_url", "image_url": {"url": img_url}})
            messages.append({"role": "user", "content": latest_content})
        else:
            messages.append({"role": "user", "content": latest_text})

        # 发起异步补全请求 (支持重试)
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = await self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    max_tokens=self.max_tokens,
                )
                raw_text = response.choices[0].message.content or ""
                # 清洗去除思考过程
                return self.stripper.strip(raw_text)

            except (APIConnectionError, APITimeoutError, APIStatusError) as e:
                logger.warning(f"大模型调用失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                if attempt == max_retries:
                    raise
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                # 收到外部任务取消（用户插话打断）
                logger.info("大模型生成任务已被取消")
                raise

        return ""

"""大语言模型异步调用客户端，支持图文多模态、时间戳注入与思考过程强制关闭。"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from openai import AsyncOpenAI, APIConnectionError, APIStatusError, APITimeoutError
from app.engine.think_stripper import ThinkStripper

logger = logging.getLogger(__name__)

# 常见 OpenAI 兼容端点用于关闭思考链的扩展参数
_THINKING_OFF_EXTRA = {
    "enable_thinking": False,
    "chat_template_kwargs": {"enable_thinking": False},
}

# 缓存不支持 extra_body 传参的 Base URL，避免重复无效尝试
_UNSUPPORTED_THINKING_ENDPOINTS: Set[str] = set()


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

    def _is_param_rejected_error(self, err: Exception) -> bool:
        """检查错误是否由服务端不识别 extra_body 引起。"""
        err_str = str(err).lower()
        param_keywords = (
            "enable_thinking",
            "chat_template_kwargs",
            "extra_body",
            "unknown parameter",
            "unrecognized",
            "unexpected keyword",
            "extra inputs",
            "not a valid parameter",
            "invalid parameter",
            "502",
            "500",
            "400",
            "422",
        )
        return any(k in err_str for k in param_keywords)

    async def generate_response(
        self,
        system_prompt: str,
        history_messages: List[Dict[str, Any]],
        new_user_text: str,
        new_image_urls: Optional[List[str]] = None,
    ) -> str:
        """组装上下文、时间戳与多模态数据并调用大模型，强制禁用思考过程。"""
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
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

        # 构建请求参数
        call_kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
        }

        # 尝试通过 extra_body 显式禁用思考
        allow_extra = self.api_base not in _UNSUPPORTED_THINKING_ENDPOINTS
        if allow_extra:
            call_kwargs["extra_body"] = _THINKING_OFF_EXTRA

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = await self._client.chat.completions.create(**call_kwargs)
                raw_text = response.choices[0].message.content or ""
                # 清洗去除所有思维链残留
                return self.stripper.strip(raw_text)

            except (APIConnectionError, APITimeoutError, APIStatusError) as e:
                # 若因 extra_body 参数被服务端拒绝，记录端点并降级重试
                if "extra_body" in call_kwargs and self._is_param_rejected_error(e):
                    logger.info(f"端点 {self.api_base} 不支持 extra_body 思考控制参数，已降级重试")
                    _UNSUPPORTED_THINKING_ENDPOINTS.add(self.api_base)
                    call_kwargs.pop("extra_body", None)
                    continue

                logger.warning(f"大模型调用失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                if attempt == max_retries:
                    raise
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                logger.info("大模型生成任务已被取消")
                raise

        return ""

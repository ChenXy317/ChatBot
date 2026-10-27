"""消息防抖与强打断调度器：支持 1.5s 缓冲与大模型回复即时撤销重置。"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional
from sqlalchemy import select
from app.core.database import async_session_factory
from app.engine.humanizer import HumanizerPipeline
from app.engine.llm_client import LLMClient
from app.engine.prompt_builder import compose_system_prompt
from app.models.orm import BotConfig, ChatMessage, SystemLog, WhitelistUser

logger = logging.getLogger(__name__)


@dataclass
class UserSessionState:
    """单个用户的会话任务与缓冲队列。"""
    pending_texts: List[str] = field(default_factory=list)
    pending_images: List[str] = field(default_factory=list)
    timer_task: Optional[asyncio.Task] = None
    generation_task: Optional[asyncio.Task] = None


class MessageDebouncer:
    """消息防抖与打断管理器。"""

    def __init__(
        self,
        send_message_fn: Callable[[int, str], Coroutine[Any, Any, None]],
        set_status_fn: Callable[[int], Coroutine[Any, Any, None]],
    ):
        self._send_message_fn = send_message_fn
        self._set_status_fn = set_status_fn
        self._state_callback = None
        self._sessions: Dict[int, UserSessionState] = {}

    def set_state_callback(self, callback) -> None:
        """注册诊断状态回调，不直接依赖网关模块。"""
        self._state_callback = callback

    def _set_state(self, value: str) -> None:
        if self._state_callback:
            self._state_callback(value)

    def get_session(self, user_id: int) -> UserSessionState:
        """获取或创建用户的会话状态。"""
        if user_id not in self._sessions:
            self._sessions[user_id] = UserSessionState()
        return self._sessions[user_id]

    async def handle_incoming_message(
        self,
        user_id: int,
        text: str,
        image_urls: Optional[List[str]] = None,
        message_id: Optional[str] = None,
    ) -> None:
        """处理接收到的私聊消息并调度防抖与打断。"""
        image_urls = image_urls or []
        state = self.get_session(user_id)
        self._set_state(f"incoming:{user_id}:{message_id or ''}")

        # 1. 如果之前正在执行大模型生成或发送，立即强制打断并丢弃
        if state.generation_task and not state.generation_task.done():
            logger.info(f"用户 {user_id} 发送新消息，强制打断正在生成的回复任务")
            state.generation_task.cancel()
            state.generation_task = None

        # 2. 如果已有防抖计时器在运行，取消旧计时器（重置 1.5s 计时）
        if state.timer_task and not state.timer_task.done():
            state.timer_task.cancel()
            state.timer_task = None

        # 3. 追加到未处理消息缓冲
        if text.strip():
            state.pending_texts.append(text.strip())
        state.pending_images.extend(image_urls)

        # 4. 启动新的 1.5s 倒计时任务
        state.timer_task = asyncio.create_task(
            self._debounce_timer(user_id)
        )

    async def _debounce_timer(self, user_id: int) -> None:
        """防抖计时器协程。"""
        # 读取当前配置中的防抖秒数
        debounce_delay = 1.5
        try:
            async with async_session_factory() as session:
                cfg_result = await session.execute(select(BotConfig).limit(1))
                cfg = cfg_result.scalar_one_or_none()
                if cfg:
                    debounce_delay = cfg.debounce_delay
        except Exception as e:
            logger.debug(f"读取防抖时间失败，使用默认 1.5 秒: {e}")

        try:
            if debounce_delay > 0:
                await asyncio.sleep(debounce_delay)
            # 倒计时结束且中途无新消息打断，开始执行大模型调用
            state = self.get_session(user_id)
            state.generation_task = asyncio.create_task(
                self._execute_llm_cycle(user_id)
            )
        except asyncio.CancelledError:
            # 倒计时被中途到来的新消息重置
            pass

    async def _execute_llm_cycle(self, user_id: int) -> None:
        """执行大模型请求与拟人化回复全生命周期。"""
        state = self.get_session(user_id)

        # 提取合并缓冲的消息
        combined_text = "\n".join(state.pending_texts)
        combined_images = list(state.pending_images)
        state.pending_texts.clear()
        state.pending_images.clear()

        if not combined_text and not combined_images:
            return

        async with async_session_factory() as session:
            # 检查总开关
            cfg_res = await session.execute(select(BotConfig).limit(1))
            cfg = cfg_res.scalar_one_or_none()
            if not cfg or not cfg.is_enabled:
                self._set_state("skipped_disabled")
                logger.info(f"自动接管未开启，跳过用户 {user_id}")
                return

            # 检查白名单
            wl_res = await session.execute(
                select(WhitelistUser).where(WhitelistUser.user_id == user_id)
            )
            wl_user = wl_res.scalar_one_or_none()
            if not wl_user or not wl_user.is_enabled:
                self._set_state(f"skipped_whitelist:{user_id}")
                logger.info(f"用户 {user_id} 不在白名单或已被停用，跳过回复")
                return
            self._set_state(f"llm_started:{user_id}")

            # 加载该好友的全部历史，按消息写入顺序正序发送给模型。
            msg_res = await session.execute(
                select(ChatMessage)
                .where(ChatMessage.user_id == user_id)
                .order_by(ChatMessage.id.asc())
            )
            raw_history = list(msg_res.scalars().all())

            # 格式化历史消息
            history_list = []
            for h in raw_history:
                history_list.append({
                    "role": h.role,
                    "content": h.content,
                    "image_urls": h.image_urls,
                    "created_at": h.created_at.strftime("%Y-%m-%d %H:%M:%S") if h.created_at else "",
                })

            # 角色设定、好友设定、输出设定按固定顺序拼接，块间保留空行。
            effective_prompt = compose_system_prompt(
                cfg.role_prompt,
                wl_user.custom_prompt,
                cfg.output_prompt,
            )

            # 构建 LLM 客户端
            llm = LLMClient(
                api_base=cfg.api_base,
                api_key=cfg.api_key,
                model=cfg.model,
                temperature=cfg.temperature,
                top_p=cfg.top_p,
                max_tokens=cfg.max_tokens,
            )
            humanizer = HumanizerPipeline(typing_speed=cfg.typing_speed)

        try:
            # 生成模型回复
            reply_text = await llm.generate_response(
                system_prompt=effective_prompt,
                history_messages=history_list,
                new_user_text=combined_text,
                new_image_urls=combined_images,
            )

            if not reply_text:
                self._set_state(f"empty_reply:{user_id}")
                return
            self._set_state(f"reply_ready:{user_id}")

            # 持久化存储用户本次发送的消息
            async with async_session_factory() as session:
                user_msg = ChatMessage(
                    user_id=user_id,
                    role="user",
                    content=combined_text,
                    image_urls=combined_images if combined_images else None,
                    created_at=datetime.now(),
                )
                session.add(user_msg)
                await session.commit()

            # 执行分句与延迟发送
            await humanizer.dispatch(
                user_id=user_id,
                raw_reply=reply_text,
                send_message_fn=self._send_message_fn,
                set_status_fn=self._set_status_fn,
            )
            self._set_state(f"sent:{user_id}")

        except asyncio.CancelledError:
            self._set_state(f"cancelled:{user_id}")
            logger.info(f"用户 {user_id} 的回复任务在执行中被强行打断，已舍弃输出")
            raise
        except Exception as e:
            self._set_state(f"error:{user_id}:{str(e)}")
            logger.error(f"处理用户 {user_id} 对话失败: {e}", exc_info=True)
            async with async_session_factory() as session:
                log_entry = SystemLog(
                    level="ERROR",
                    source="DEBOUNCER",
                    message=f"回复用户 {user_id} 异常: {str(e)}",
                )
                session.add(log_entry)
                await session.commit()

"""OneBot v11 反向 WebSocket 网关，负责与 NapCatQQ 维持长连接与消息解包。"""

import asyncio
import base64
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import delete, select
from app.core.config import settings
from app.core.database import async_session_factory
from app.engine.debouncer import MessageDebouncer
from app.engine.duplicate_guard import MessageDeduplicator
from app.models.orm import ChatMessage, SystemLog, WhitelistUser

logger = logging.getLogger(__name__)

# 好友清空上下文指令集合
CLEAR_COMMANDS = {
    "/clear",
    "／clear",
    "/clean",
    "／clean",
    "/reset",
    "／reset",
    "清空上下文",
    "清除上下文",
    "清空记忆",
    "清除记忆",
    "重置对话",
    "清空历史",
}


@dataclass
class ExtractedMessage:
    """解析后的消息内容，以及需要向 NapCat 补取 URL 的图片引用。"""
    text: str
    image_urls: List[str] = field(default_factory=list)
    unresolved_images: List[str] = field(default_factory=list)


class OneBotGateway:
    """OneBot v11 协议通信网关。"""

    def __init__(self):
        self.active_socket: Optional[WebSocket] = None
        self.debouncer: Optional[MessageDebouncer] = None
        self._action_counter = 0
        self.current_qq: Optional[str] = None
        self.current_nickname: Optional[str] = None
        self._pending_actions: Dict[str, asyncio.Future] = {}
        self.last_event: Dict[str, Any] = {}
        self.last_debouncer_state: str = "idle"
        self._deduplicator = MessageDeduplicator()

    def set_debouncer(self, debouncer: MessageDebouncer) -> None:
        """注册消息防抖调度器。"""
        self.debouncer = debouncer

    @property
    def is_connected(self) -> bool:
        """检查 NapCat 当前是否在线连接。"""
        return self.active_socket is not None

    async def send_action(
        self,
        action: str,
        params: Dict[str, Any],
        echo: Optional[str] = None,
        wait_response: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """通过反向 WebSocket 调用 OneBot API，并按需等待回执。"""
        if not self.active_socket:
            logger.warning("NapCat 尚未连接，无法执行 API 调用")
            return None

        self._action_counter += 1
        request_id = echo or f"req_{self._action_counter}"
        payload = {
            "action": action,
            "params": params,
            "echo": request_id,
        }
        response_future = None
        if wait_response:
            response_future = asyncio.get_running_loop().create_future()
            self._pending_actions[request_id] = response_future
        try:
            await self.active_socket.send_text(json.dumps(payload, ensure_ascii=False))
            if response_future:
                return await asyncio.wait_for(response_future, timeout=5.0)
        except asyncio.TimeoutError:
            logger.error(f"等待 OneBot 指令回执超时 ({action})")
            return None
        except Exception as e:
            logger.error(f"发送 OneBot 指令失败 ({action}): {e}")
            return None
        finally:
            if response_future:
                self._pending_actions.pop(request_id, None)
        return None

    def is_self_message(self, event: Dict[str, Any]) -> bool:
        """拒绝 self_id 与 user_id 相同的消息，避免自动回复形成回环。"""
        self_id = event.get("self_id")
        user_id = event.get("user_id")
        return bool(self_id and user_id and str(self_id) == str(user_id))

    async def send_private_message(self, user_id: int, message: str) -> None:
        """向指定 QQ 好友发送私聊文本消息。"""
        response = await self.send_action(
            "send_private_msg",
            {"user_id": user_id, "message": message},
            wait_response=True,
        )
        if not response or response.get("status") == "failed" or response.get("retcode", 0) != 0:
            raise RuntimeError(f"QQ 消息发送失败: {response}")

    async def set_input_status(self, user_id: int) -> None:
        """将私聊窗口置为“正在输入中...”状态。"""
        await self.send_action("set_input_status", {"user_id": user_id, "status": 1})

    @staticmethod
    def _normalize_image_source(data: Dict[str, Any]) -> Optional[str]:
        """从 OneBot 图片段中挑选可继续解析的图片地址或内部文件标识。"""
        for key in ("url", "image_url", "file", "file_id"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _image_data_url(value: str) -> Optional[str]:
        """把图片地址或 base64 数据统一成 OpenAI 支持的内容地址。"""
        if value.startswith(("data:image/", "http://", "https://")):
            return value
        if value.startswith("base64://"):
            return f"data:image/jpeg;base64,{value[9:]}"
        return None

    @staticmethod
    def _local_image_data_url(value: str) -> Optional[str]:
        """把 NapCat 下载到本机的图片转成 data URI。"""
        try:
            path = Path(value)
            if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
                return None
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        except (OSError, ValueError):
            return None

        suffix = path.suffix.lower()
        mime_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }.get(suffix, "image/jpeg")
        return f"data:{mime_type};base64,{encoded}"

    def extract_message_content(self, raw_data: Dict[str, Any]) -> Tuple[str, List[str]]:
        """兼容旧调用方，返回文字与全部图片地址/文件标识。"""
        extracted = self.parse_message_content(raw_data)
        return extracted.text, extracted.image_urls + extracted.unresolved_images

    def parse_message_content(self, raw_data: Dict[str, Any]) -> ExtractedMessage:
        """解析消息段，并区分可用图片与需要向 NapCat 补取地址的图片。"""
        message_obj = raw_data.get("message")
        raw_message = raw_data.get("raw_message", "")

        texts: List[str] = []
        image_urls: List[str] = []
        unresolved_images: List[str] = []

        # 优先解析结构化消息段列表
        if isinstance(message_obj, list):
            for seg in message_obj:
                seg_type = seg.get("type")
                data = seg.get("data", {})
                if seg_type == "text":
                    text_val = data.get("text", "")
                    if text_val:
                        texts.append(text_val)
                elif seg_type == "image":
                    encoded = data.get("base64")
                    if isinstance(encoded, str) and encoded.strip():
                        encoded = encoded.strip()
                        if not encoded.startswith("base64://"):
                            encoded = f"base64://{encoded}"
                        image_data = self._image_data_url(encoded)
                        if image_data:
                            image_urls.append(image_data)
                            continue

                    source = self._normalize_image_source(data)
                    if source:
                        image_data = self._image_data_url(source)
                        if image_data:
                            image_urls.append(image_data)
                        else:
                            unresolved_images.append(source)

        # 兼容 CQ 码格式
        if isinstance(message_obj, str) or not message_obj:
            for params in re.findall(r"\[CQ:image,([^\]]+)\]", raw_message):
                parsed = dict(
                    item.split("=", 1)
                    for item in params.split(",")
                    if "=" in item
                )
                source = parsed.get("url") or parsed.get("file")
                if not source:
                    continue
                source = source.replace("&amp;", "&")
                image_data = self._image_data_url(source)
                if image_data:
                    image_urls.append(image_data)
                else:
                    unresolved_images.append(source)

            # 过滤掉 CQ 码得到纯文本
            clean_text = re.sub(r"\[CQ:[^\]]+\]", "", raw_message).strip()
            if clean_text:
                texts.append(clean_text)

        final_text = " ".join(texts).strip()
        return ExtractedMessage(
            text=final_text,
            image_urls=image_urls,
            unresolved_images=unresolved_images,
        )

    async def resolve_image_urls(self, image_sources: List[str]) -> List[str]:
        """对缺少 URL 的图片调用 NapCat get_image，失败时记录并跳过。"""
        resolved: List[str] = []
        for source in image_sources:
            response = await self.send_action(
                "get_image",
                {"file": source},
                wait_response=True,
            )
            if not response:
                logger.warning("NapCat 未能返回图片信息: %s", source)
                continue
            if response.get("status") == "failed" or response.get("retcode", 0) != 0:
                logger.warning("NapCat 获取图片失败: %s (%s)", source, response)
                continue
            data = response.get("data") or {}
            for key in ("base64", "url", "file"):
                value = data.get(key)
                if not isinstance(value, str) or not value.strip():
                    continue
                if key == "base64":
                    value = self._image_data_url(value)
                elif not value.startswith(("http://", "https://")):
                    value = self._local_image_data_url(value)
                if value:
                    resolved.append(value)
                    break
        return resolved

    async def handle_websocket(self, websocket: WebSocket) -> None:
        """处理来自 NapCat 的反向 WebSocket 客户端连接。"""
        authorization = websocket.headers.get("authorization", "").strip()
        if authorization.lower().startswith("bearer "):
            supplied_token = authorization[7:].strip()
        elif authorization.lower().startswith("token "):
            supplied_token = authorization[6:].strip()
        else:
            supplied_token = authorization
        client_host = websocket.client.host if websocket.client else ""
        is_loopback = client_host in ("127.0.0.1", "::1", "localhost", "testclient")
        if settings.ONEBOT_WS_TOKEN:
            if supplied_token != settings.ONEBOT_WS_TOKEN:
                if is_loopback and not supplied_token:
                    logger.info("允许来自本机 loopback 的 OneBot 反向 WebSocket 连接")
                else:
                    await websocket.close(code=1008, reason="Unauthorized")
                    logger.warning(f"拒绝未通过 OneBot WebSocket token 校验的连接 (来源: {client_host})")
                    return

        await websocket.accept()
        self.active_socket = websocket
        
        # 尝试从握手请求头提取登录账号
        client_self_id = websocket.headers.get("x-self-id")
        if client_self_id:
            self.current_qq = str(client_self_id)
            
        logger.info(f"NapCatQQ 协议端已连接 (账号: {self.current_qq or '未知'})")

        # 异步拉取当前登录者资料
        await self.send_action("get_login_info", {}, echo="init_login_info")

        try:
            while True:
                msg_text = await websocket.receive_text()
                try:
                    event = json.loads(msg_text)
                except Exception:
                    continue

                echo = event.get("echo")
                if echo and echo in self._pending_actions:
                    response_future = self._pending_actions[echo]
                    if not response_future.done():
                        response_future.set_result(event)
                    continue

                self.last_event = {
                    "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "post_type": event.get("post_type") or "",
                    "message_type": event.get("message_type") or "",
                    "user_id": str(event.get("user_id") or ""),
                    "self_id": str(event.get("self_id") or ""),
                    "action": "received",
                }
                logger.debug("收到 OneBot 事件: %s", self.last_event)

                # 记录协议端汇报的 self_id
                if "self_id" in event and event["self_id"]:
                    self.current_qq = str(event["self_id"])

                # 处理主动查询的登录信息回执
                if event.get("echo") == "init_login_info":
                    data = event.get("data") or {}
                    if "user_id" in data:
                        self.current_qq = str(data["user_id"])
                    if "nickname" in data:
                        self.current_nickname = str(data["nickname"])
                    logger.info(f"已同步当前 QQ 资料: {self.current_nickname} ({self.current_qq})")
                    continue

                # 忽略心跳与生命周期广播
                if event.get("post_type") == "meta_event":
                    continue

                # 仅处理私聊消息事件
                if event.get("post_type") == "message" and event.get("message_type") == "private":
                    if self.is_self_message(event):
                        self.last_event["action"] = "ignored_self"
                        logger.debug("忽略机器人自身发送的私聊消息")
                        continue

                    user_id = event.get("user_id")
                    if not user_id:
                        self.last_event["action"] = "ignored_no_user"
                        continue

                    # 图片段通常只有内部 file ID，需要额外请求 get_image 才能拿到 URL。
                    extracted = self.parse_message_content(event)
                    if (
                        not extracted.text
                        and not extracted.image_urls
                        and not extracted.unresolved_images
                    ):
                        self.last_event["action"] = "ignored_empty"
                        continue

                    images = list(extracted.image_urls)
                    if extracted.unresolved_images:
                        images.extend(await self.resolve_image_urls(extracted.unresolved_images))
                    text = extracted.text
                    if not text and not images:
                        self.last_event["action"] = "ignored_unreadable_image"
                        logger.warning(
                            "收到好友 [%s] 的图片消息，但未能取得可访问的图片地址",
                            user_id,
                        )
                        continue

                    logger.info(f"收到好友 [{user_id}] 消息: {text} (图片: {len(images)} 张)")
                    message_id = str(event.get("message_id") or "")
                    if not self._deduplicator.accept(message_id):
                        self.last_event["action"] = "ignored_duplicate"
                        logger.info("忽略重复私聊消息: message_id=%s", message_id)
                        continue

                    # 处理清空上下文指令
                    cmd = text.strip().lower().rstrip("!！.。~～")
                    if cmd in CLEAR_COMMANDS:
                        async with async_session_factory() as session:
                            wl_res = await session.execute(
                                select(WhitelistUser).where(WhitelistUser.user_id == user_id)
                            )
                            wl_user = wl_res.scalar_one_or_none()
                            if not wl_user or not wl_user.is_enabled:
                                logger.info(f"用户 {user_id} 发送清空指令但未在白名单启用，跳过")
                                self.last_event["action"] = "ignored_non_whitelist"
                                continue

                            if self.debouncer:
                                self.debouncer.clear_session(user_id)

                            await session.execute(
                                delete(ChatMessage).where(ChatMessage.user_id == user_id)
                            )
                            log_entry = SystemLog(
                                level="INFO",
                                source="GATEWAY",
                                message=f"好友 {user_id} 发送指令 [{text.strip()}] 清空了上下文记忆",
                            )
                            session.add(log_entry)
                            await session.commit()

                        logger.info(f"已清空好友 [{user_id}] 上下文记忆")
                        try:
                            await self.send_private_message(user_id, "已清空当前会话的上下文记忆。")
                        except Exception as e:
                            logger.error(f"发送清空上下文确认消息失败: {e}")
                        self.last_event["action"] = "cleared_context"
                        continue

                    self.last_event["action"] = "queued"

                    if self.debouncer:
                        logger.info(
                            "转发私聊消息: message_id=%s user_id=%s",
                            event.get("message_id"),
                            user_id,
                        )
                        # 投递至防抖与打断引擎
                        asyncio.create_task(
                            self.debouncer.handle_incoming_message(
                                user_id=user_id,
                                text=text,
                                image_urls=images,
                                message_id=message_id,
                            )
                        )

        except WebSocketDisconnect:
            logger.warning("NapCatQQ 连接已断开")
        except Exception as e:
            logger.error(f"WebSocket 运行时异常: {e}")
        finally:
            for response_future in self._pending_actions.values():
                if not response_future.done():
                    response_future.cancel()
            self._pending_actions.clear()
            self.active_socket = None
            self.current_qq = None
            self.current_nickname = None


gateway = OneBotGateway()

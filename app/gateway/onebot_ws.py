"""OneBot v11 反向 WebSocket 网关，负责与 NapCatQQ 维持长连接与消息解包。"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from fastapi import WebSocket, WebSocketDisconnect
from app.core.config import settings
from app.engine.debouncer import MessageDebouncer
from app.engine.duplicate_guard import MessageDeduplicator

logger = logging.getLogger(__name__)


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

    def extract_message_content(self, raw_data: Dict[str, Any]) -> Tuple[str, List[str]]:
        """从 OneBot 消息事件中提取纯文本与图片链接列表。"""
        message_obj = raw_data.get("message")
        raw_message = raw_data.get("raw_message", "")
        
        texts: List[str] = []
        image_urls: List[str] = []

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
                    url = data.get("url") or data.get("file")
                    if url and (url.startswith("http://") or url.startswith("https://")):
                        image_urls.append(url)

        # 兼容 CQ 码格式
        if not texts and raw_message:
            # 提取 CQ 码图片 URL
            cq_images = re.findall(r"\[CQ:image,[^\]]*url=([^,\]]+)", raw_message)
            image_urls.extend(cq_images)
            # 过滤掉 CQ 码得到纯文本
            clean_text = re.sub(r"\[CQ:[^\]]+\]", "", raw_message).strip()
            if clean_text:
                texts.append(clean_text)

        final_text = " ".join(texts).strip()
        return final_text, image_urls

    async def handle_websocket(self, websocket: WebSocket) -> None:
        """处理来自 NapCat 的反向 WebSocket 客户端连接。"""
        authorization = websocket.headers.get("authorization", "").strip()
        if authorization.lower().startswith("bearer "):
            supplied_token = authorization[7:].strip()
        elif authorization.lower().startswith("token "):
            supplied_token = authorization[6:].strip()
        else:
            supplied_token = authorization
        if supplied_token != settings.ONEBOT_WS_TOKEN:
            await websocket.close(code=1008, reason="Unauthorized")
            logger.warning("拒绝未通过 OneBot WebSocket token 校验的连接")
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

                    # 提取文字与多模态图片
                    text, images = self.extract_message_content(event)
                    if not text and not images:
                        self.last_event["action"] = "ignored_empty"
                        continue

                    logger.info(f"收到好友 [{user_id}] 消息: {text} (图片: {len(images)} 张)")
                    message_id = str(event.get("message_id") or "")
                    if not self._deduplicator.accept(message_id):
                        self.last_event["action"] = "ignored_duplicate"
                        logger.info("忽略重复私聊消息: message_id=%s", message_id)
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

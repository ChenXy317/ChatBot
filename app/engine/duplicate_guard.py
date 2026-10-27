"""短期消息去重，避免 NapCat 在重连或会话同步时重复投递。"""

from collections import OrderedDict
from threading import Lock


class MessageDeduplicator:
    """按消息 ID 保留最近一段时间的消息指纹。"""

    def __init__(self, max_items: int = 500):
        self._max_items = max_items
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._lock = Lock()

    def accept(self, message_id: str) -> bool:
        """首次出现返回 True，重复消息返回 False。"""
        if not message_id:
            return True
        with self._lock:
            if message_id in self._seen:
                self._seen.move_to_end(message_id)
                return False
            self._seen[message_id] = None
            while len(self._seen) > self._max_items:
                self._seen.popitem(last=False)
            return True

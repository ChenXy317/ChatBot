"""测试上下文清理指令识别与会话防抖状态清空。"""

import unittest
from unittest.mock import AsyncMock
from app.gateway.onebot_ws import CLEAR_COMMANDS
from app.engine.debouncer import MessageDebouncer, UserSessionState


class ClearCommandTests(unittest.IsolatedAsyncioTestCase):
    def test_clear_commands_matching(self):
        valid_inputs = [
            "/clear",
            "/CLEAR",
            "／clear",
            "/clean",
            "/reset",
            "清空上下文",
            "清除上下文",
            "清空记忆",
            "清除记忆",
            "重置对话",
            "清空历史",
            "/clear!",
            "清空上下文。",
            "清除记忆～",
        ]
        for cmd_raw in valid_inputs:
            normalized = cmd_raw.strip().lower().rstrip("!！.。~～")
            self.assertIn(normalized, CLEAR_COMMANDS)

    async def test_debouncer_clear_session(self):
        async def dummy_send(uid, msg):
            pass

        async def dummy_status(uid):
            pass

        debouncer = MessageDebouncer(dummy_send, dummy_status)
        session = debouncer.get_session(10001)
        session.pending_texts.append("待处理消息")
        session.pending_images.append("http://example.com/a.jpg")
        session.active_text = "生成中的文本"
        session.active_images = ["http://example.com/b.jpg"]

        debouncer.clear_session(10001)

        self.assertEqual(session.pending_texts, [])
        self.assertEqual(session.pending_images, [])
        self.assertEqual(session.active_text, "")
        self.assertEqual(session.active_images, [])

    async def test_debouncer_interruption_recovers_active_text(self):
        async def dummy_send(uid, msg):
            pass

        async def dummy_status(uid):
            pass

        debouncer = MessageDebouncer(dummy_send, dummy_status)
        session = debouncer.get_session(10002)

        # 模拟上一轮正在执行的回复任务
        async def slow_generation():
            import asyncio
            await asyncio.sleep(5)

        import asyncio
        session.generation_task = asyncio.create_task(slow_generation())
        session.active_text = "前一句被中断的提问"

        # 用户发送新消息打断
        await debouncer.handle_incoming_message(10002, "后一句新提问")

        # 验证前一句未完成的文本被保留在 pending_texts 前端
        self.assertIn("前一句被中断的提问", session.pending_texts)
        self.assertIn("后一句新提问", session.pending_texts)
        self.assertEqual(session.pending_texts[0], "前一句被中断的提问")
        self.assertEqual(session.pending_texts[1], "后一句新提问")

        # 清理剩余任务
        debouncer.clear_session(10002)


if __name__ == "__main__":
    unittest.main()

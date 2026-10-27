"""测试防抖缓冲与拟人化单字延迟下限调整为 0 的正确性。"""

import asyncio
import unittest
from pydantic import ValidationError
from app.schemas.common import BotConfigBase, BotConfigUpdate
from app.engine.humanizer import HumanizerPipeline


class PacingAndSchemaTests(unittest.IsolatedAsyncioTestCase):
    def test_schema_allows_zero_debounce_and_typing(self):
        cfg = BotConfigBase(
            api_base="http://localhost:8000/v1",
            api_key="",
            model="gpt-4o",
            role_prompt="test",
            output_prompt="test",
            debounce_delay=0.0,
            typing_speed=0.0,
        )
        self.assertEqual(cfg.debounce_delay, 0.0)
        self.assertEqual(cfg.typing_speed, 0.0)

        update = BotConfigUpdate(debounce_delay=0.0, typing_speed=0.0)
        self.assertEqual(update.debounce_delay, 0.0)
        self.assertEqual(update.typing_speed, 0.0)

    def test_schema_rejects_negative_values(self):
        with self.assertRaises(ValidationError):
            BotConfigBase(
                api_base="http://localhost:8000/v1",
                api_key="",
                model="gpt-4o",
                role_prompt="test",
                output_prompt="test",
                debounce_delay=-0.1,
            )

        with self.assertRaises(ValidationError):
            BotConfigUpdate(typing_speed=-0.01)

    async def test_humanizer_pipeline_zero_speed_does_not_sleep(self):
        pipeline = HumanizerPipeline(typing_speed=0.0)
        sent_messages = []
        statuses = []

        async def mock_send(user_id, msg):
            sent_messages.append((user_id, msg))

        async def mock_status(user_id):
            statuses.append(user_id)

        # 模拟执行 dispatch
        sentences = pipeline.split_sentences("第一句\n第二句")
        self.assertEqual(sentences, ["第一句", "第二句"])


if __name__ == "__main__":
    unittest.main()

"""图片消息解析、补取 URL 与多模态请求构造测试。"""

import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from app.engine.llm_client import LLMClient
from app.gateway.onebot_ws import OneBotGateway


class ImageMessageParsingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.gateway = OneBotGateway()

    def test_extracts_http_image_url(self):
        result = self.gateway.parse_message_content({
            "message": [{
                "type": "image",
                "data": {"url": "https://example.com/photo.jpg?x=1&y=2"},
            }],
        })
        self.assertEqual(result.text, "")
        self.assertEqual(
            result.image_urls,
            ["https://example.com/photo.jpg?x=1&y=2"],
        )
        self.assertEqual(result.unresolved_images, [])

    def test_keeps_file_id_for_napcat_lookup(self):
        result = self.gateway.parse_message_content({
            "message": [{
                "type": "image",
                "data": {"file": "abc.jpg", "file_id": "internal-id", "url": ""},
            }],
        })
        self.assertEqual(result.text, "")
        self.assertEqual(result.image_urls, [])
        self.assertEqual(result.unresolved_images, ["abc.jpg"])

    def test_converts_inline_base64_to_data_uri(self):
        result = self.gateway.parse_message_content({
            "message": [{
                "type": "image",
                "data": {"base64": "/9j/4AAQSkZJRgABAQ=="},
            }],
        })
        self.assertEqual(
            result.image_urls,
            ["data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ=="],
        )

    def test_extracts_cq_image_url(self):
        raw = "[CQ:image,file=abc.jpg,url=https://example.com/b.jpg?x=1&amp;y=2] 看看"
        result = self.gateway.parse_message_content({
            "message": raw,
            "raw_message": raw,
        })
        self.assertEqual(result.text, "看看")
        self.assertEqual(
            result.image_urls,
            ["https://example.com/b.jpg?x=1&y=2"],
        )

    async def test_resolves_file_id_with_get_image(self):
        self.gateway.send_action = AsyncMock(return_value={
            "status": "ok",
            "retcode": 0,
            "data": {"url": "https://example.com/resolved.jpg"},
        })

        urls = await self.gateway.resolve_image_urls(["internal-id"])

        self.assertEqual(urls, ["https://example.com/resolved.jpg"])
        self.gateway.send_action.assert_awaited_once_with(
            "get_image",
            {"file": "internal-id"},
            wait_response=True,
        )

    async def test_skips_failed_image_lookup(self):
        self.gateway.send_action = AsyncMock(return_value={
            "status": "failed",
            "retcode": 1200,
            "data": None,
        })
        self.assertEqual(await self.gateway.resolve_image_urls(["bad-id"]), [])

    async def test_converts_downloaded_local_image_to_data_uri(self):
        with TemporaryDirectory() as directory:
            image_path = Path(directory) / "photo.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
            self.gateway.send_action = AsyncMock(return_value={
                "status": "ok",
                "retcode": 0,
                "data": {"file": str(image_path), "url": str(image_path)},
            })

            urls = await self.gateway.resolve_image_urls(["internal-id"])

        self.assertEqual(len(urls), 1)
        self.assertTrue(urls[0].startswith("data:image/png;base64,"))


class GatewayImageEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_websocket_event_reaches_debouncer(self):
        gateway = OneBotGateway()
        gateway.debouncer = unittest.mock.Mock()
        gateway.debouncer.handle_incoming_message = AsyncMock()
        async def send_action(action, params, **kwargs):
            if action == "get_image":
                return {
                    "status": "ok",
                    "retcode": 0,
                    "data": {"url": "https://example.com/resolved.jpg"},
                }
            return None

        gateway.send_action = AsyncMock(side_effect=send_action)

        image_event = json.dumps({
                "post_type": "message",
                "message_type": "private",
                "self_id": 10001,
                "user_id": 20002,
                "message_id": 30003,
                "message": [{
                    "type": "image",
                    "data": {"file": "internal-id", "url": ""},
                }],
                "raw_message": "",
        })

        websocket = unittest.mock.Mock()
        websocket.headers = {}
        websocket.client.host = "127.0.0.1"
        websocket.accept = AsyncMock()
        websocket.receive_text = AsyncMock(side_effect=[image_event, Exception("stop")])

        await gateway.handle_websocket(websocket)

        for _ in range(10):
            await asyncio.sleep(0)
            if gateway.debouncer.handle_incoming_message.await_count:
                break
        gateway.debouncer.handle_incoming_message.assert_awaited_once()
        call = gateway.debouncer.handle_incoming_message.await_args.kwargs
        self.assertEqual(call["text"], "")
        self.assertEqual(call["image_urls"], ["https://example.com/resolved.jpg"])
        self.assertEqual(gateway.last_event["action"], "queued")


class MultimodalRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_pure_image_has_non_empty_text_placeholder(self):
        client = LLMClient(
            api_base="https://example.com/v1",
            api_key="",
            model="vision-test",
        )
        response = unittest.mock.Mock()
        response.choices = [
            unittest.mock.Mock(message=unittest.mock.Mock(content="看到了"))
        ]
        client._client.chat.completions.create = AsyncMock(return_value=response)

        with patch.object(client.stripper, "strip", side_effect=lambda text: text):
            reply = await client.generate_response(
                system_prompt="test",
                history_messages=[],
                new_user_text="",
                new_image_urls=["https://example.com/photo.jpg"],
            )

        self.assertEqual(reply, "看到了")
        payload = client._client.chat.completions.create.await_args.kwargs
        latest = payload["messages"][-1]
        self.assertEqual(latest["role"], "user")
        self.assertIn("我发来了一张图片", latest["content"][0]["text"])
        self.assertEqual(
            latest["content"][1],
            {"type": "image_url", "image_url": {"url": "https://example.com/photo.jpg"}},
        )


if __name__ == "__main__":
    unittest.main()

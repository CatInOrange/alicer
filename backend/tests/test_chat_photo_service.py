from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.db import Database
from app.services.chat_photo_service import _build_image_prompt, _run_chat_photo_task


class FakeImageLlm:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.fail_first = fail_first
        self.prompts: list[str] = []

    async def generate_image(self, *, prompt: str, bucket: str = "chat", reference_image_url: str | None = None) -> dict:
        self.prompts.append(prompt)
        if self.fail_first and len(self.prompts) == 1:
            raise RuntimeError("image provider returned 400: imagine:content-moderated")
        return {
            "imageUrl": "/uploads/chat/test.jpg",
            "provider": {"configured": True, "bucket": bucket, "referenceImageUrl": reference_image_url},
        }


class ChatPhotoServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmpdir.name) / "test.db")
        self.db.ensure_schema()
        self.settings = {
            "companion": {"name": "苏晚秋", "userName": "郎君"},
            "moments": {"referenceImageUrl": "https://example.com/ref.jpg"},
        }

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_build_image_prompt_sanitizes_moderation_risky_terms(self) -> None:
        prompt = _build_image_prompt(
            self.settings,
            {
                "scene": "酒店镜前，浴袍半挂",
                "outfit": "黑丝和吊带",
                "pose": "突出腿线，很撩人",
                "mood": "性感诱惑",
            },
            companion="苏晚秋",
            user_name="郎君",
        )

        for forbidden in ("浴袍半挂", "黑丝", "丝袜", "吊带", "腿线", "撩人", "性感", "诱惑", "裸"):
            self.assertNotIn(forbidden, prompt)
        self.assertIn("fully clothed", prompt)

    async def test_moderation_failure_retries_with_safe_fallback_and_sends_photo(self) -> None:
        task = self.db.create_chat_photo_task(
            task_id="photo_test",
            source="requested",
            requested_by_message_id="user_1",
            assistant_text_message_id="assistant_1",
            prompt={"scene": "酒店镜前，浴袍半挂", "outfit": "丝袜"},
            image_prompt=_build_image_prompt(
                self.settings,
                {"scene": "酒店镜前，浴袍半挂", "outfit": "丝袜"},
                companion="苏晚秋",
                user_name="郎君",
            ),
            caption="拍好了。",
            date_key="2026-07-17",
        )
        llm = FakeImageLlm(fail_first=True)

        await _run_chat_photo_task(self.db, llm, settings=self.settings, task=task)  # type: ignore[arg-type]

        self.assertEqual(len(llm.prompts), 2)
        self.assertIn("fully clothed", llm.prompts[0])
        self.assertIn("hotel window", llm.prompts[1])
        saved = self.db.get_chat_photo_task("photo_test")
        self.assertIsNotNone(saved)
        self.assertEqual(saved["status"], "sent")
        self.assertEqual(saved["imageUrl"], "/uploads/chat/test.jpg")
        self.assertTrue(saved["metadata"]["safePromptFallback"])
        self.assertEqual(saved["metadata"]["attempts"][0]["status"], "failed")
        self.assertEqual(saved["metadata"]["attempts"][1]["status"], "ok")
        messages = self.db.list_messages(limit=10)
        self.assertEqual(messages[-1]["metadata"]["kind"], "chat_photo")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.db import Database
from app.services.moment_service import generate_moment


class FakeLlm:
    def __init__(self) -> None:
        self.messages: list[list[dict]] = []

    async def complete(self, *, messages: list[dict], model_settings: dict) -> str:
        self.messages.append(messages)
        return '{"content":"今天的光线很好，偷偷留一张。","imagePrompt":"窗边随手拍，浅色上衣，自然光","moodTag":"日常"}'


class MomentServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmpdir.name) / "test.db")
        self.db.ensure_schema()
        self.llm = FakeLlm()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    async def test_generate_moment_persists_moment_and_fact(self) -> None:
        result = await generate_moment(
            self.db,
            self.llm,  # type: ignore[arg-type]
            settings={
                "companion": {"name": "苏晚秋", "userName": "你"},
                "moments": {"dailyPostProbability": 1.0, "photoProbability": 0.0},
                "life": {"enabled": False},
                "model": {"model": "fake"},
                "promptModules": [],
            },
            force=True,
            source="test",
        )

        self.assertTrue(result["created"])
        moment = result["moment"]
        self.assertEqual(moment["author"], "苏晚秋")
        self.assertEqual(moment["metadata"]["source"], "test")
        self.assertEqual(self.db.list_moments(limit=10)[0]["id"], moment["id"])
        facts = self.db.list_life_facts(statuses=["active"], include_expired=True, limit=10)
        self.assertEqual(facts[0]["type"], "moment_posted")
        self.assertEqual(facts[0]["related"]["momentId"], moment["id"])


if __name__ == "__main__":
    unittest.main()

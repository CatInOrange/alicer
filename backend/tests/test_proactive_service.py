from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from app.db import Database
from app.services.proactive_service import TZ, _build_candidates, run_proactive_once


class FakeLlm:
    def __init__(self) -> None:
        self.messages: list[list[dict]] = []

    async def complete(self, *, messages: list[dict], model_settings: dict) -> str:
        self.messages.append(messages)
        content = "\n".join(str(item.get("content") or "") for item in messages)
        if "字段：activity" in content:
            return (
                '{"activity":"晚间放松","location":"家","mood":"柔软",'
                '"energy":0.45,"summary":"窝在自己的小空间里放松。",'
                '"details":"灯光很安静。","continuity":"延续晚间节奏。","canPostMoment":true}'
            )
        return "刚刚想到你。忙的话不用急着回，我就是轻轻碰一下你的袖子。"


class ProactiveServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmpdir.name) / "test.db")
        self.db.ensure_schema()
        self.llm = FakeLlm()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    async def test_idle_chat_delivers_proactive_message(self) -> None:
        old_message = self.db.add_message(
            message_id="msg_user_old",
            role="user",
            content="我今天可能会很忙。",
        )
        self._set_message_time(old_message["id"], dt.datetime.now(TZ).timestamp() - 8 * 3600)

        result = await run_proactive_once(
            self.db,
            self.llm,  # type: ignore[arg-type]
            settings=self._settings(),
            force=False,
        )

        self.assertTrue(result["created"])
        self.assertEqual(result["type"], "chat")
        messages = self.db.list_messages(limit=10)
        self.assertEqual(messages[-1]["role"], "assistant")
        self.assertEqual(messages[-1]["metadata"]["source"], "proactive")
        events = self.db.list_proactive_events(limit=10)
        self.assertEqual(events[0]["status"], "delivered")
        self.assertEqual(events[0]["eventType"], "chat")

    async def test_below_threshold_records_skip_without_message(self) -> None:
        recent = self.db.add_message(
            message_id="msg_user_recent",
            role="user",
            content="我先忙一下。",
        )
        self._set_message_time(recent["id"], dt.datetime.now(TZ).timestamp() - 2 * 3600)

        result = await run_proactive_once(
            self.db,
            self.llm,  # type: ignore[arg-type]
            settings=self._settings({"minIdleHoursBeforeChat": 1, "chatThreshold": 0.99}),
            force=False,
        )

        self.assertFalse(result["created"])
        self.assertEqual(result["reason"], "below_threshold")
        messages = self.db.list_messages(limit=10)
        self.assertEqual(len(messages), 1)
        events = self.db.list_proactive_events(limit=10)
        self.assertEqual(events[0]["status"], "skipped")

    def test_question_about_companion_is_not_follow_up_candidate(self) -> None:
        message = {
            "id": "msg_question",
            "role": "user",
            "content": "哈哈哈，穿好丝袜出门了？",
            "createdAt": dt.datetime.now(TZ).timestamp() - 2 * 3600,
            "metadata": {},
        }

        candidates = _build_candidates(
            settings=self._settings({"minIdleHoursBeforeChat": 10}),
            now=dt.datetime.now(TZ),
            recent_messages=[message],
            recent_moments=[],
            recent_proactive=[],
            life_context={"state": {}},
            user_context={},
            allow_moments=False,
        )

        self.assertFalse([item for item in candidates if item.intent == "follow_up"])

    def _settings(self, proactive_overrides: dict | None = None) -> dict:
        proactive = {
            "enabled": True,
            "quietHours": {"start": "00:00", "end": "00:00"},
            "minIdleHoursBeforeChat": 5,
            "minHoursBetweenChat": 3,
            "minHoursBetweenMoments": 8,
            "maxChatPerDay": 3,
            "maxMomentsPerDay": 2,
            "chatThreshold": 0.66,
            "momentThreshold": 0.68,
        }
        proactive.update(proactive_overrides or {})
        return {
            "companion": {"name": "苏晚秋", "userName": "你"},
            "memory": {"longTerm": True},
            "environment": {"time": True},
            "life": {"enabled": True, "updateIntervalHours": 1},
            "userTimeline": {"enabled": False},
            "chatPhotos": {"enabled": False},
            "proactive": proactive,
            "model": {"model": "fake"},
        }

    def _set_message_time(self, message_id: str, created_at: float) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE messages SET created_at = ? WHERE id = ?",
                (created_at, message_id),
            )


if __name__ == "__main__":
    unittest.main()

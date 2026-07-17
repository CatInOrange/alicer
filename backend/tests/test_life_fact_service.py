from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from app.db import Database
from app.services.life_fact_service import TZ, cleanup_life_facts, extract_life_facts


class FakeLlm:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.messages: list[dict] = []

    async def complete(self, *, messages: list[dict], model_settings: dict) -> str:
        self.messages = messages
        return json.dumps(self.payload, ensure_ascii=False)


class LifeFactServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmpdir.name) / "test.db")
        self.db.ensure_schema()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    async def test_relative_tomorrow_uses_message_time_and_4am_boundary(self) -> None:
        anchor = dt.datetime(2026, 7, 18, 2, 0, tzinfo=TZ)
        llm = FakeLlm(
            {
                "facts": [
                    {
                        "type": "schedule_commitment",
                        "title": "明天早上要去机场",
                        "summary": "明天早上出门去机场。",
                        "confidence": 0.82,
                        "importance": 0.8,
                        "status": "planned",
                    }
                ]
            }
        )

        facts = await extract_life_facts(
            self.db,
            llm,  # type: ignore[arg-type]
            settings={},
            user_message={
                "id": "msg_user",
                "content": "你明天要做什么？",
                "createdAt": anchor.timestamp(),
            },
            assistant_message={
                "id": "msg_assistant",
                "content": "明天早上要去机场。",
                "createdAt": anchor.timestamp() + 10,
            },
        )

        self.assertEqual(len(facts), 1)
        start = dt.datetime.fromtimestamp(float(facts[0]["startsAt"]), tz=TZ)
        self.assertEqual(start.date(), dt.date(2026, 7, 18))
        self.assertEqual(start.hour, 9)
        self.assertNotIn("明天", facts[0]["title"])
        prompt_payload = json.loads(llm.messages[1]["content"])
        self.assertEqual(prompt_payload["userMessage"]["createdAt"], anchor.isoformat())
        self.assertEqual(prompt_payload["userLifeDay"], "2026-07-17")

    def test_cleanup_supersedes_duplicate_active_facts(self) -> None:
        starts_at = dt.datetime(2026, 7, 18, 9, 0, tzinfo=TZ).timestamp()
        self.db.upsert_life_fact(
            fact_id="fact_old",
            fact_type="schedule_commitment",
            status="planned",
            title="07-18 去机场",
            summary="07-18 早上去机场。",
            starts_at=starts_at,
            confidence=0.6,
            importance=0.5,
            source="chat",
            source_message_id="msg_1",
        )
        self.db.upsert_life_fact(
            fact_id="fact_new",
            fact_type="schedule_commitment",
            status="planned",
            title="07-18 去机场",
            summary="07-18 早上去机场。",
            starts_at=starts_at,
            confidence=0.9,
            importance=0.8,
            source="chat",
            source_message_id="msg_1",
        )

        result = cleanup_life_facts(
            self.db,
            now=dt.datetime(2026, 7, 17, 12, 0, tzinfo=TZ).timestamp(),
        )

        self.assertEqual(result["supersededDuplicates"], 1)
        self.assertEqual(self.db.get_life_fact("fact_old")["status"], "superseded")
        self.assertEqual(self.db.get_life_fact("fact_new")["status"], "planned")


if __name__ == "__main__":
    unittest.main()

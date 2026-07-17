from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from app.db import Database
from app.services.life_fact_service import TZ, cleanup_life_facts, extract_life_facts, resolve_life_constraints_for_day
from app.services.life_service import _effective_profile, _fallback_plan, _normalize_plan


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

    def test_cleanup_completes_ended_active_fact_before_expiring(self) -> None:
        end = dt.datetime(2026, 7, 17, 21, 0, tzinfo=TZ).timestamp()
        self.db.upsert_life_fact(
            fact_id="fact_flight_done",
            fact_type="schedule_commitment",
            status="active",
            title="北京至大连航班15:00-21:00",
            summary="苏晚秋执飞北京至大连航班，预计21:00落地。",
            starts_at=dt.datetime(2026, 7, 17, 15, 0, tzinfo=TZ).timestamp(),
            ends_at=end,
            expires_at=end,
            confidence=1.0,
            importance=0.8,
            source="chat",
        )

        result = cleanup_life_facts(
            self.db,
            now=dt.datetime(2026, 7, 17, 23, 30, tzinfo=TZ).timestamp(),
        )

        self.assertEqual(result["completed"], 1)
        self.assertEqual(self.db.get_life_fact("fact_flight_done")["status"], "completed")

    def test_resolve_constraints_turns_flight_into_hard_blocks_and_conflicts(self) -> None:
        day = dt.date(2026, 7, 17)
        flight_start = dt.datetime(2026, 7, 17, 15, 0, tzinfo=TZ).timestamp()
        flight_end = dt.datetime(2026, 7, 17, 21, 0, tzinfo=TZ).timestamp()
        self.db.upsert_life_fact(
            fact_id="fact_flight",
            fact_type="schedule_commitment",
            status="planned",
            title="北京至大连航班15:00-21:00",
            summary="苏晚秋于2026-07-17 15:00执飞北京至大连航线，预计21:00落地。",
            starts_at=flight_start,
            ends_at=flight_end,
            confidence=1.0,
            importance=0.8,
            source="chat",
        )
        self.db.upsert_life_fact(
            fact_id="fact_coffee",
            fact_type="relationship_commitment",
            status="planned",
            title="若用户14点前未出现则去温泉镇送咖啡",
            summary="如果用户在2026-07-17 14:00之前没有出现，苏晚秋将去温泉镇送咖啡。",
            starts_at=dt.datetime(2026, 7, 17, 14, 0, tzinfo=TZ).timestamp(),
            ends_at=dt.datetime(2026, 7, 17, 16, 0, tzinfo=TZ).timestamp(),
            confidence=0.8,
            importance=0.7,
            source="chat",
        )

        constraints = resolve_life_constraints_for_day(self.db, day, {})

        activities = " ".join(item["activity"] for item in constraints["hardBlocks"])
        self.assertIn("前往机场", activities)
        self.assertIn("北京至大连航班", activities)
        self.assertIn("机场", constraints["allowedLocations"])
        self.assertTrue(constraints["conflicts"])
        self.assertEqual(constraints["conflicts"][0]["factId"], "fact_coffee")

    def test_normalize_plan_inserts_hard_blocks_and_removes_conflicting_soft_events(self) -> None:
        day = dt.date(2026, 7, 17)
        start = dt.datetime(2026, 7, 17, 15, 0, tzinfo=TZ).timestamp()
        end = dt.datetime(2026, 7, 17, 21, 0, tzinfo=TZ).timestamp()
        self.db.upsert_life_fact(
            fact_id="fact_flight",
            fact_type="schedule_commitment",
            status="planned",
            title="北京至大连航班15:00-21:00",
            summary="苏晚秋于2026-07-17 15:00执飞北京至大连航线，预计21:00落地。",
            starts_at=start,
            ends_at=end,
            confidence=1.0,
            importance=0.8,
            source="chat",
        )
        constraints = resolve_life_constraints_for_day(self.db, day, {})
        plan = _normalize_plan(
            {
                "dayTheme": "错误地在家待客",
                "plannedEvents": [
                    {"timeRange": "14:00-16:30", "activity": "去温泉镇送咖啡", "location": "温泉镇", "intent": "履行承诺"},
                    {"timeRange": "18:00-19:00", "activity": "在家做饭", "location": "家", "intent": "晚饭"},
                ],
            },
            profile={"homeBase": "家", "usualPlaces": ["家"], "routine": {}},
            slot=dt.datetime(2026, 7, 17, 10, 0, tzinfo=TZ),
            source="test",
            life_constraints=constraints,
        )

        text = json.dumps(plan["plannedEvents"], ensure_ascii=False)
        self.assertIn("北京至大连航班", text)
        self.assertIn("前往机场", text)
        self.assertIn('"certainty": "hard"', text)
        self.assertNotIn("去温泉镇送咖啡", text)

    def test_effective_profile_and_routine_keep_flight_jobs_and_rest_days_coherent(self) -> None:
        day = dt.date(2026, 7, 17)
        self.db.upsert_life_fact(
            fact_id="fact_flight",
            fact_type="schedule_commitment",
            status="planned",
            title="下午3点执飞航班",
            summary="苏晚秋在2026-07-17 15:00有一趟航班。",
            starts_at=dt.datetime(2026, 7, 17, 15, 0, tzinfo=TZ).timestamp(),
            confidence=0.9,
            importance=0.7,
            source="chat",
        )
        constraints = resolve_life_constraints_for_day(self.db, day, {})

        profile = _effective_profile(
            {"occupation": "普通上班族", "workStyle": "office", "homeBase": "家", "usualPlaces": ["家"]},
            life_constraints=constraints,
        )

        self.assertEqual(profile["occupation"], "空乘")
        self.assertEqual(profile["workStyle"], "roster")
        self.assertIn("机场", profile["usualPlaces"])

        saturday_plan = _fallback_plan(
            profile={"occupation": "普通上班族", "workStyle": "office", "homeBase": "家", "usualPlaces": ["家"]},
            slot=dt.datetime(2026, 7, 18, 10, 0, tzinfo=TZ),
        )
        weekend_text = json.dumps(saturday_plan["plannedEvents"], ensure_ascii=False)
        self.assertIn("休息", saturday_plan["dayTheme"])
        self.assertIn("兼职", weekend_text)
        self.assertNotIn("09:00-12:00\", \"activity\": \"处理主要事务\"", weekend_text)

        roster_plan = _fallback_plan(
            profile=profile,
            slot=dt.datetime(2026, 7, 18, 10, 0, tzinfo=TZ),
        )
        roster_text = json.dumps(roster_plan["plannedEvents"], ensure_ascii=False)
        self.assertIn("备勤", roster_text)
        self.assertIn("没有明确航班时不强行执飞", roster_text)


if __name__ == "__main__":
    unittest.main()

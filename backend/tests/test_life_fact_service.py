from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from app.db import Database
from app.services.life_fact_service import (
    TZ,
    cleanup_life_facts,
    extract_life_facts,
    extract_life_facts_batch,
    reflect_life_fact_retention,
    refresh_life_facts_from_recent_chat,
    resolve_life_constraints_for_day,
)
from app.services.life_service import (
    _build_week_plan,
    _effective_profile,
    _fallback_plan,
    _normalize_plan,
    choose_moment_life_event,
)


class FakeLlm:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.messages: list[dict] = []
        self.all_messages: list[list[dict]] = []
        self.calls = 0

    async def complete(self, *, messages: list[dict], model_settings: dict) -> str:
        self.calls += 1
        self.messages = messages
        self.all_messages.append(messages)
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

    async def test_reconcile_refreshes_today_plan_after_plan_affecting_fact(self) -> None:
        now = dt.datetime.now(TZ).replace(minute=0, second=0, microsecond=0)
        start = now
        end = start + dt.timedelta(hours=3)
        llm = FakeLlm(
            {
                "facts": [
                    {
                        "type": "schedule_commitment",
                        "title": "今天下午执飞航班",
                        "summary": "今天下午有一趟已确定航班。",
                        "startsAt": start.isoformat(),
                        "endsAt": end.isoformat(),
                        "confidence": 0.9,
                        "importance": 0.8,
                        "status": "planned",
                    }
                ]
            }
        )

        facts = await extract_life_facts(
            self.db,
            llm,  # type: ignore[arg-type]
            settings={"life": {"enabled": True}},
            user_message={
                "id": "msg_user_reconcile",
                "content": "你今天下午是不是要飞？",
                "createdAt": now.timestamp(),
            },
            assistant_message={
                "id": "msg_assistant_reconcile",
                "content": "嗯，今天下午有一趟航班。",
                "createdAt": now.timestamp() + 10,
            },
            reconcile=True,
        )

        self.assertEqual(len(facts), 1)
        job = self.db.get_scheduled_job("consistency:life_projection:last")
        self.assertIsNotNone(job)
        self.assertTrue(job["result"]["refreshedTodayPlan"])
        plan = (self.db.get_life_state() or {}).get("plan") or {}
        hard_blocks = json.dumps(plan.get("hardBlocks") or [], ensure_ascii=False)
        self.assertIn(facts[0]["id"], hard_blocks)
        self.assertIn("航班", hard_blocks)

    async def test_batch_extracts_multiple_pairs_with_one_llm_call(self) -> None:
        anchor = dt.datetime(2026, 7, 21, 12, 48, tzinfo=TZ)
        llm = FakeLlm(
            {
                "facts": [
                    {
                        "sourcePairId": "msg_user_jeans:msg_assistant_jeans",
                        "type": "relationship_commitment",
                        "title": "去太古里挑选微喇牛仔裤并拍照给用户验收",
                        "summary": "苏晚秋在2026-07-21 12:48承诺直接去太古里挑选微喇牛仔裤，并在试衣间拍照给用户验收。",
                        "confidence": 0.78,
                        "importance": 0.65,
                        "status": "planned",
                        "metadata": {
                            "targetDate": "2026-07-21",
                            "timeHint": "afternoon",
                            "commitmentStrength": "accepted",
                            "flexibility": "soft",
                        },
                    }
                ]
            }
        )

        facts = await extract_life_facts_batch(
            self.db,
            llm,  # type: ignore[arg-type]
            settings={},
            pairs=[
                (
                    {
                        "id": "msg_user_coffee",
                        "content": "你到冷萃店拍张咖啡杯影子照吧",
                        "createdAt": anchor.timestamp() - 60,
                    },
                    {
                        "id": "msg_assistant_coffee",
                        "content": "行，到店我拍给你看。",
                        "createdAt": anchor.timestamp() - 50,
                    },
                ),
                (
                    {
                        "id": "msg_user_jeans",
                        "content": "下午去太古里买条牛仔裤，我喜欢微喇那种，拍张照给我看看",
                        "createdAt": anchor.timestamp(),
                    },
                    {
                        "id": "msg_assistant_jeans",
                        "content": "行，那我直接拐去太古里给你挑微喇裤，试衣间拍给你验收。",
                        "createdAt": anchor.timestamp() + 10,
                    },
                ),
            ],
        )

        self.assertEqual(llm.calls, 1)
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["metadata"]["sourcePairId"], "msg_user_jeans:msg_assistant_jeans")
        self.assertEqual(facts[0]["metadata"]["targetDate"], "2026-07-21")
        prompt_payload = json.loads(llm.messages[1]["content"])
        self.assertEqual(len(prompt_payload["conversationPairs"]), 2)

    async def test_refresh_batches_candidates_and_skips_processed_pairs(self) -> None:
        today = dt.datetime.now(TZ).date().isoformat()
        self.db.add_message(message_id="msg_user_old", role="user", content="明天下午去机场吗？")
        self.db.add_message(message_id="msg_assistant_old", role="assistant", content="嗯，明天下午去机场。")
        self.db.upsert_life_fact(
            fact_id="fact_old",
            fact_type="schedule_commitment",
            status="planned",
            title="07-22 下午去机场",
            summary="苏晚秋在2026-07-22下午去机场。",
            source="chat",
            source_message_id="msg_user_old",
            related={"userMessageId": "msg_user_old", "assistantMessageId": "msg_assistant_old", "sourcePairId": "msg_user_old:msg_assistant_old"},
            metadata={"sourcePairId": "msg_user_old:msg_assistant_old"},
        )
        self.db.add_message(
            message_id="msg_user_new",
            role="user",
            content="下午去太古里买条牛仔裤，我喜欢微喇那种，拍张照给我看看",
        )
        self.db.add_message(
            message_id="msg_assistant_new",
            role="assistant",
            content="行，那我直接拐去太古里给你挑微喇裤，试衣间拍给你验收。",
        )
        llm = FakeLlm(
            {
                "facts": [
                    {
                        "sourcePairId": "msg_user_new:msg_assistant_new",
                        "type": "relationship_commitment",
                        "title": "去太古里挑选微喇牛仔裤并拍照给用户验收",
                        "summary": "苏晚秋承诺去太古里挑选微喇牛仔裤，并拍照给用户验收。",
                        "confidence": 0.8,
                        "importance": 0.65,
                        "status": "planned",
                        "metadata": {"targetDate": today, "commitmentStrength": "accepted", "flexibility": "soft"},
                    }
                ]
            }
        )

        result = await refresh_life_facts_from_recent_chat(self.db, llm, settings={}, limit=10)  # type: ignore[arg-type]

        self.assertEqual(llm.calls, 2)
        prompt_payload = json.loads(llm.all_messages[0][1]["content"])
        self.assertEqual(len(prompt_payload["conversationPairs"]), 1)
        self.assertEqual(result["candidatePairs"], 2)
        self.assertEqual(result["pendingPairs"], 1)
        self.assertEqual(result["batchPairs"], 1)
        self.assertEqual(len(result["savedFacts"]), 1)

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

    def test_retention_promotes_old_valuable_fact_to_memory(self) -> None:
        end = dt.datetime(2026, 7, 15, 20, 0, tzinfo=TZ).timestamp()
        self.db.upsert_life_fact(
            fact_id="fact_relationship_rule",
            fact_type="relationship_commitment",
            status="completed",
            title="以后记住纪念日要提前准备",
            summary="苏晚秋答应以后记住纪念日，并提前准备一点仪式感。",
            ends_at=end,
            confidence=0.9,
            importance=0.82,
            source="chat",
        )

        result = reflect_life_fact_retention(
            self.db,
            now=dt.datetime(2026, 7, 18, 21, 0, tzinfo=TZ).timestamp(),
            force=True,
        )

        fact = self.db.get_life_fact("fact_relationship_rule")
        memory = self.db.get_memory("mem_life_fact_fact_relationship_rule")
        self.assertEqual(result["memoriesCreated"], 1)
        self.assertEqual(fact["metadata"]["retentionDisposition"], "promoted_to_memory")
        self.assertIsNotNone(memory)
        self.assertEqual(memory["kind"], "relationship")
        self.assertIn("纪念日", memory["content"])

    def test_retention_archives_old_low_value_fact(self) -> None:
        end = dt.datetime(2026, 7, 15, 10, 0, tzinfo=TZ).timestamp()
        self.db.upsert_life_fact(
            fact_id="fact_old_errand",
            fact_type="schedule_commitment",
            status="completed",
            title="去楼下买水",
            summary="苏晚秋去楼下便利店买水。",
            ends_at=end,
            confidence=0.74,
            importance=0.3,
            source="chat",
        )

        result = reflect_life_fact_retention(
            self.db,
            now=dt.datetime(2026, 7, 18, 21, 0, tzinfo=TZ).timestamp(),
            force=True,
        )

        fact = self.db.get_life_fact("fact_old_errand")
        self.assertEqual(result["archivedLowValue"], 1)
        self.assertEqual(fact["status"], "archived")
        self.assertEqual(fact["metadata"]["retentionDisposition"], "archived_low_value")
        self.assertIsNone(self.db.get_memory("mem_life_fact_fact_old_errand"))

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

    def test_week_plan_uses_roster_draft_without_hard_facts(self) -> None:
        start_day = dt.date(2026, 7, 22)
        profile = {
            "occupation": "空乘",
            "workStyle": "roster",
            "homeBase": "家",
            "usualPlaces": ["家", "机场"],
            "routine": {
                "type": "roster",
                "workDaysPerMonth": "14-18",
                "maxConsecutiveWorkDays": 4,
                "minRestAfterFlightHours": 12,
                "possibleDuties": ["执飞", "备勤", "培训", "调休", "个人安排/兼职"],
            },
        }

        week_plan = _build_week_plan(
            self.db,
            settings={},
            profile=profile,
            start_day=start_day,
            recent_events=[],
        )

        day_types = {item["dayType"] for item in week_plan["days"]}
        self.assertNotEqual(day_types, {"roster_unknown"})
        self.assertIn("draft", {item["certainty"] for item in week_plan["days"]})
        draft_text = json.dumps(week_plan, ensure_ascii=False)
        self.assertIn("未锁定", draft_text)
        self.assertNotRegex(draft_text, r"[A-Z]{2}\d{3,4}")

    def test_week_plan_hard_fact_overrides_roster_draft(self) -> None:
        day = dt.date(2026, 7, 23)
        self.db.upsert_life_fact(
            fact_id="fact_flight_hard",
            fact_type="schedule_commitment",
            status="planned",
            title="下午执飞航班",
            summary="苏晚秋在2026-07-23 15:00执飞一趟航班。",
            starts_at=dt.datetime(2026, 7, 23, 15, 0, tzinfo=TZ).timestamp(),
            ends_at=dt.datetime(2026, 7, 23, 19, 0, tzinfo=TZ).timestamp(),
            confidence=0.9,
            importance=0.8,
            source="chat",
        )

        week_plan = _build_week_plan(
            self.db,
            settings={},
            profile={"occupation": "空乘", "workStyle": "roster", "homeBase": "家", "usualPlaces": ["家", "机场"]},
            start_day=dt.date(2026, 7, 22),
            recent_events=[],
        )

        target = next(item for item in week_plan["days"] if item["date"] == day.isoformat())
        self.assertEqual(target["confidence"], "hard")
        self.assertEqual(target["certainty"], "hard")
        self.assertEqual(target["dayType"], "work")
        self.assertTrue(target["hardBlocks"])

    def test_draft_aviation_event_is_not_selected_for_moment(self) -> None:
        slot = dt.datetime(2026, 7, 22, 14, 0, tzinfo=TZ)
        self.db.add_life_event(
            event_id="life_draft_aviation",
            event_time=slot.timestamp(),
            activity="可能执飞或航班任务",
            location="机场/航站楼",
            mood="平稳",
            energy=0.55,
            summary="按周草稿去机场附近等待排班。",
            can_post_moment=True,
            metadata={"planBlock": {"certainty": "draft", "activity": "可能执飞或航班任务", "location": "机场/航站楼"}},
        )
        self.db.add_life_event(
            event_id="life_normal",
            event_time=(slot - dt.timedelta(hours=1)).timestamp(),
            activity="午饭和休息",
            location="家",
            mood="放松",
            energy=0.6,
            summary="午饭后慢慢休息。",
            can_post_moment=True,
            metadata={},
        )

        selected = choose_moment_life_event(self.db)

        self.assertIsNotNone(selected)
        self.assertEqual(selected["id"], "life_normal")


if __name__ == "__main__":
    unittest.main()

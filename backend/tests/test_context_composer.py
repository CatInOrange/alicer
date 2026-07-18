from __future__ import annotations

import datetime as dt
import unittest
from zoneinfo import ZoneInfo

from app.services.context_composer import compose_prompt_context


TZ = ZoneInfo("Asia/Shanghai")


class ContextComposerTest(unittest.TestCase):
    def test_context_brief_includes_future_timeline_and_hard_blocks(self) -> None:
        composed = compose_prompt_context(
            settings={"memory": {"longTerm": True}, "environment": {"time": True}, "companion": {"name": "苏晚秋"}},
            recent_messages=[],
            memories=[],
            environment={"time": "2026-07-17 12:30"},
            life_context={
                "enabled": True,
                "state": {"activity": "午饭后整理飞行包", "location": "家"},
                "plan": {
                    "date": "2026-07-17",
                    "dayTheme": "航班日",
                    "source": "test",
                    "generatedAt": "2026-07-17T12:00:00+08:00",
                    "plannedEvents": [
                        {
                            "timeRange": "13:30-15:00",
                            "activity": "前往机场和值机准备",
                            "location": "机场",
                            "intent": "为下午航班做准备",
                            "certainty": "hard",
                            "source": "fact",
                        },
                        {
                            "timeRange": "15:00-21:00",
                            "activity": "执飞北京至大连航班",
                            "location": "机上",
                            "intent": "硬事实锁定",
                            "certainty": "hard",
                            "source": "fact",
                        },
                    ],
                    "hardBlocks": [
                        {
                            "timeRange": "15:00-21:00",
                            "activity": "执飞北京至大连航班",
                            "location": "机上",
                            "intent": "硬事实锁定",
                            "certainty": "hard",
                            "source": "fact",
                        }
                    ],
                },
                "lifeConstraints": {
                    "hardBlocks": [
                        {
                            "timeRange": "15:00-21:00",
                            "activity": "执飞北京至大连航班",
                            "location": "机上",
                            "intent": "硬事实锁定",
                        }
                    ],
                    "conflicts": [{"message": "温泉镇送咖啡被航班阻断，不能安排在下午。"}],
                },
                "routine": {"type": "roster"},
                "recentEvents": [],
                "updatedAt": 1784259000,
            },
            user_context={"enabled": False},
            photo_context={"enabled": False},
            world_context={
                "upcoming": [],
                "stable": [],
                "activeFacts": [],
                "freshness": {
                    "latestFactUpdatedAt": 1784259300,
                    "lastReconciliation": {
                        "ranAt": 1784259400,
                        "result": {"sourceReason": "test", "refreshedTodayPlan": True},
                    },
                },
            },
        )

        brief = composed["variables"]["context.brief"]
        future = composed["variables"]["world.future"]
        freshness = composed["package"]["freshness"]
        self.assertIn("Alicer 未来时间线", brief)
        self.assertIn("投影新鲜度", brief)
        self.assertIn("最近一致性调和", composed["variables"]["context.freshness"])
        self.assertEqual(freshness["planGeneratedAt"], "2026-07-17T12:00:00+08:00")
        self.assertEqual(freshness["lastReconciliation"]["sourceReason"], "test")
        self.assertIn("未来回答规则", future)
        self.assertIn("执飞北京至大连航班", brief)
        self.assertIn("硬日程", brief)
        self.assertIn("温泉镇送咖啡被航班阻断", brief)
        self.assertIn("排班制", brief)

    def test_stale_life_state_is_not_presented_as_current(self) -> None:
        stale_state_at = dt.datetime(2026, 7, 18, 4, 0, tzinfo=TZ).timestamp()
        top_level_updated_at = dt.datetime(2026, 7, 18, 10, 6, tzinfo=TZ).timestamp()
        composed = compose_prompt_context(
            settings={
                "memory": {"longTerm": True},
                "environment": {"time": True},
                "life": {"updateIntervalHours": 6},
                "companion": {"name": "苏晚秋"},
            },
            recent_messages=[],
            memories=[],
            environment={"time": "2026-07-18 10:06"},
            life_context={
                "enabled": True,
                "state": {
                    "activity": "睡眠中",
                    "location": "大连/酒店客房",
                    "summary": "凌晨四点的酒店房间，大连的海风依然温柔。",
                    "updatedAt": stale_state_at,
                },
                "plan": {
                    "date": "2026-07-18",
                    "plannedEvents": [
                        {
                            "timeRange": "09:30-10:30",
                            "activity": "航前准备",
                            "location": "大连机场",
                            "intent": "准备返京航班",
                            "certainty": "planned",
                        },
                        {
                            "timeRange": "10:30-11:45",
                            "activity": "执飞大连至北京航班",
                            "location": "机上",
                            "certainty": "hard",
                        },
                    ],
                },
                "lifeConstraints": {},
                "routine": {},
                "recentEvents": [],
                "updatedAt": top_level_updated_at,
            },
            user_context={"enabled": False},
            photo_context={"enabled": False},
            world_context={"activeFacts": [], "freshness": {}},
        )

        current = composed["variables"]["world.current"]
        freshness = composed["package"]["freshness"]
        self.assertIn("当前真实时间（Asia/Shanghai）：2026-07-18 10:06", current)
        self.assertIn("北京时间=大连时间，不存在时差", current)
        self.assertIn("上次生活模拟状态", current)
        self.assertIn("可能已过期", current)
        self.assertIn("按今日计划当前/下一段参考", current)
        self.assertIn("航前准备", current)
        self.assertNotIn("生活模拟当前状态：睡眠中", current)
        self.assertNotIn("当前片段：凌晨四点", current)
        self.assertEqual(freshness["lifeStateUpdatedAt"], stale_state_at)

    def test_fresh_life_state_still_appears_as_current(self) -> None:
        state_at = dt.datetime(2026, 7, 18, 10, 0, tzinfo=TZ).timestamp()
        composed = compose_prompt_context(
            settings={
                "memory": {"longTerm": True},
                "environment": {"time": True},
                "life": {"updateIntervalHours": 1},
            },
            recent_messages=[],
            memories=[],
            environment={"time": "2026-07-18 10:06"},
            life_context={
                "enabled": True,
                "state": {
                    "activity": "航前准备",
                    "location": "大连机场",
                    "summary": "在机组休息室确认航班信息。",
                    "updatedAt": state_at,
                },
                "plan": {},
                "lifeConstraints": {},
                "routine": {},
                "recentEvents": [],
            },
            user_context={"enabled": False},
            photo_context={"enabled": False},
            world_context={"activeFacts": [], "freshness": {}},
        )

        current = composed["variables"]["world.current"]
        self.assertIn("生活模拟当前状态：航前准备", current)
        self.assertIn("当前片段：在机组休息室确认航班信息", current)
        self.assertNotIn("可能已过期", current)

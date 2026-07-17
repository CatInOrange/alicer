from __future__ import annotations

import unittest

from app.services.context_composer import compose_prompt_context


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

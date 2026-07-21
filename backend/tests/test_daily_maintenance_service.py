from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from app.db import Database
from app.routers.diary import _diary_system_prompt, _diary_user_prompt
from app.services.daily_maintenance_service import (
    TZ,
    get_daily_maintenance_status,
    run_daily_maintenance_once,
)


class FakeLlm:
    async def complete(self, *, messages: list[dict], model_settings: dict) -> str:
        content = "\n".join(str(item.get("content") or "") for item in messages)
        if "记忆整理器" in content:
            return "not json"
        return "## 昨天的一点记录\n\n今天我们聊得不多，但这些安静也被好好收起来了。"


class DailyMaintenanceServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmpdir.name) / "test.db")
        self.db.ensure_schema()
        self.llm = FakeLlm()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    async def test_daily_maintenance_runs_housekeeping_and_records_summary(self) -> None:
        old_end = (dt.datetime.now(TZ) - dt.timedelta(days=3)).timestamp()
        self.db.upsert_life_fact(
            fact_id="fact_old_relationship",
            fact_type="relationship_commitment",
            status="completed",
            title="以后记住纪念日",
            summary="苏晚秋答应以后记住纪念日。",
            ends_at=old_end,
            confidence=0.9,
            importance=0.84,
            source="test",
        )
        self.db.enqueue_memory_message(
            message_id="msg_memory",
            role="user",
            content="记住我不喜欢太甜的饮料。",
            trigger_type="explicit",
        )

        result = await run_daily_maintenance_once(
            self.db,
            self.llm,  # type: ignore[arg-type]
            settings={
                "life": {"enabled": False},
                "dailyMaintenance": {"enabled": True},
                "memory": {"autoExtract": True, "reviewBeforeSave": False},
            },
            source="test",
        )

        self.assertTrue(result["ok"])
        self.assertIn("diary", result["steps"])
        self.assertEqual(result["steps"]["memory"]["created"], 1)
        self.assertEqual(result["steps"]["factRetention"]["memoriesCreated"], 1)
        self.assertIn("consistency", result["steps"])
        self.assertTrue(result["steps"]["consistency"]["processed"])
        self.assertIsNotNone(
            self.db.get_scheduled_job("daily_maintenance:consistency:last")
        )
        self.assertEqual(self.db.count_pending_memory_queue(), 0)
        self.assertIsNotNone(self.db.get_scheduled_job("daily_maintenance:last"))
        self.assertEqual(
            self.db.get_life_fact("fact_old_relationship")["metadata"][
                "retentionDisposition"
            ],
            "promoted_to_memory",
        )

        status = get_daily_maintenance_status(self.db)
        self.assertIsNotNone(status["lastRun"])
        self.assertIsNotNone(status["lastConsistency"])
        self.assertIsNone(status["lastError"])
        self.assertEqual(
            status["lastConsistency"]["result"]["metrics"]["targetDay"],
            result["targetDay"],
        )

    def test_diary_prompt_prioritizes_user_life_over_companion_life(self) -> None:
        system = _diary_system_prompt(
            "week",
            {"companion": {"name": "苏晚秋", "userName": "猫哥"}},
        )
        user = _diary_user_prompt(
            "week",
            "2026-W29",
            {
                "companionName": "苏晚秋",
                "userName": "猫哥",
                "chatMessages": [
                    {
                        "speaker": "苏晚秋",
                        "role": "assistant",
                        "roleMeaning": "伴侣回复",
                        "content": "我刚下飞机，主人你到啦？",
                    },
                ],
            },
        )

        self.assertIn("为猫哥写", system)
        self.assertIn("第一人称“我”只能指苏晚秋", system)
        self.assertIn("绝不能替猫哥自述", system)
        self.assertIn("用户这段时间的生活", system)
        self.assertIn("你的生活只能作为关系背景", system)
        self.assertIn("不要把你的模拟生活", system)
        self.assertIn("作者/叙述者：苏晚秋；记录对象：猫哥", user)
        self.assertIn("用户生活记录", user)
        self.assertIn("用户事实的唯一直接来源", user)
        self.assertIn("伴侣回复里的第一人称事件", user)
        self.assertIn("不能写成用户下飞机/用户纹身", user)
        self.assertIn("不能当作用户事实", user)
        self.assertIn("不要用伴侣自己的经历填充篇幅", user)


if __name__ == "__main__":
    unittest.main()

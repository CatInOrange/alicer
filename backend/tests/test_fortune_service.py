from __future__ import annotations

import datetime as dt
import unittest

from app.services.context_composer import compose_prompt_context
from app.services.fortune_service import build_daily_fortune_context


class FortuneServiceTest(unittest.TestCase):
    def test_daily_fortune_builds_structured_evidence_from_birthday(self) -> None:
        fortune = build_daily_fortune_context(
            {
                "fortune": {
                    "enabled": True,
                    "birthday": "1998-04-12",
                    "includeInContext": True,
                    "orbDegrees": 6,
                }
            },
            date=dt.date(2026, 7, 20),
        )

        self.assertTrue(fortune["configured"])
        self.assertEqual(fortune["birthday"], "1998-04-12")
        self.assertEqual(fortune["date"], "2026-07-20")
        self.assertIn("summary", fortune)
        self.assertIn("sourceRefs", fortune)
        self.assertIn("major_aspects", fortune["sourceRefs"])
        self.assertIn("LLM 只能转述结构化结果", "；".join(fortune["guardrails"]))
        self.assertTrue(fortune["signals"])
        first = fortune["signals"][0]
        self.assertIn("transitPlanetLabel", first)
        self.assertIn("aspectLabel", first)
        self.assertIn("natalPlanetLabel", first)
        self.assertIn("sourceRefs", first)
        self.assertIn("依据：", fortune["prompt"])

    def test_missing_birthday_is_not_injected_as_prediction(self) -> None:
        fortune = build_daily_fortune_context(
            {"fortune": {"enabled": True, "birthday": ""}},
            date=dt.date(2026, 7, 20),
        )

        self.assertFalse(fortune["configured"])
        self.assertEqual(fortune["reason"], "birthday is required")
        self.assertEqual(fortune["prompt"], "")

    def test_context_brief_includes_configured_daily_fortune(self) -> None:
        composed = compose_prompt_context(
            settings={
                "memory": {"longTerm": True},
                "environment": {"time": True},
                "fortune": {
                    "enabled": True,
                    "birthday": "1998-04-12",
                    "includeInContext": True,
                    "orbDegrees": 6,
                },
            },
            recent_messages=[],
            memories=[],
            environment={"time": "2026-07-20 08:00"},
            life_context={"enabled": False},
            user_context={"enabled": False},
            photo_context={"enabled": False},
            world_context={"activeFacts": [], "freshness": {}},
        )

        brief = composed["variables"]["context.brief"]
        self.assertIn("今日个人化运势", brief)
        self.assertIn("西洋占星行运", brief)
        self.assertIn("娱乐和自我观察", brief)


if __name__ == "__main__":
    unittest.main()

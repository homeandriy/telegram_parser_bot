from datetime import datetime, timezone
import unittest

from telegram_parser.domain.models import TelegramMessage
from telegram_parser.domain.rules import evaluate_scenarios


class ScenarioRulesTest(unittest.TestCase):
    def message(self, text: str) -> TelegramMessage:
        return TelegramMessage("public", "radar", "1", text, datetime.now(timezone.utc), "https://t.me/radar/1")

    def test_independent_scenarios_are_case_insensitive(self) -> None:
        rule = {
            "operator": "and",
            "items": [
                {"type": "condition", "mode": "contains", "value": "балістика"},
                {"type": "condition", "mode": "contains", "value": "київ"},
                {"type": "group", "scenario": True, "operator": "and", "items": [{"type": "condition", "mode": "contains", "value": "реактивний"}], "action": {}},
            ],
            "action": {},
        }
        matches = evaluate_scenarios(self.message("РЕАКТИВНИЙ дрон"), rule)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].index, 2)


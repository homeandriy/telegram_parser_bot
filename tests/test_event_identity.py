from datetime import datetime, timezone
import unittest

from telegram_parser.domain.models import TelegramMessage
from telegram_parser.domain.rules import describe_scenarios, evaluate_scenarios
from telegram_parser.infrastructure.storage import event_idempotency_key


class EventIdentityTest(unittest.TestCase):
    def test_key_is_stable_for_one_message_and_rule(self) -> None:
        message = TelegramMessage("public", "radar", "42", "Балістика на Київ", datetime.now(timezone.utc), "https://t.me/radar/42")

        self.assertEqual(
            event_idempotency_key(message, "scenario:radar:1"),
            event_idempotency_key(message, "scenario:radar:1"),
        )

    def test_key_changes_for_another_rule(self) -> None:
        message = TelegramMessage("public", "radar", "42", "Балістика на Київ", datetime.now(timezone.utc), "https://t.me/radar/42")

        self.assertNotEqual(
            event_idempotency_key(message, "scenario:radar:1"),
            event_idempotency_key(message, "scenario:radar:2"),
        )

    def test_named_scenario_is_exposed_and_matched_by_its_stable_id(self) -> None:
        rule = {
            "items": [
                {
                    "scenario": True,
                    "id": "shaheds-kyiv",
                    "title": "Шахеди на Київ",
                    "operator": "and",
                    "items": [
                        {"type": "condition", "mode": "contains", "value": "🛵"},
                        {"type": "condition", "mode": "contains", "value": "Троя"},
                    ],
                }
            ]
        }
        message = TelegramMessage("public", "radar", "42", "🛵 Троя рухається", datetime.now(timezone.utc), "https://t.me/radar/42")

        self.assertEqual(["shaheds-kyiv"], [item.id for item in describe_scenarios(rule)])
        self.assertEqual("shaheds-kyiv", evaluate_scenarios(message, rule)[0].rule_id)

    def test_ballistics_rule_matches_each_requested_variant(self) -> None:
        rule = {
            "items": [{
                "scenario": True,
                "id": "ballistics-kyiv",
                "title": "Балістика на Київ",
                "operator": "or",
                "items": [
                    {"type": "condition", "mode": "contains", "value": "Кількісна балістика"},
                    {"operator": "and", "items": [
                        {"type": "condition", "mode": "contains", "value": "Балістика"},
                        {"type": "condition", "mode": "contains", "value": "Київ"},
                    ]},
                    {"operator": "and", "items": [
                        {"type": "condition", "mode": "contains", "value": "балістики"},
                        {"type": "condition", "mode": "contains", "value": "Київ"},
                    ]},
                ],
            }],
        }
        for index, text in enumerate(("Кількісна балістика", "Балістика на Київ", "Пуск балістики у Київ")):
            message = TelegramMessage("public", "radar", str(index), text, datetime.now(timezone.utc), "https://t.me/radar/42")
            self.assertEqual(["ballistics-kyiv"], [match.rule_id for match in evaluate_scenarios(message, rule)])

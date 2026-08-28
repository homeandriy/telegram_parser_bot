from datetime import datetime, timezone
import unittest

from telegram_parser.models import TelegramMessage
from telegram_parser.rules import evaluate


class RulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.message = TelegramMessage("test", "channel", "1", "Балістика на Київ. Негайно в укриття", datetime.now(timezone.utc), "https://example.test/1")

    def test_critical_rule_has_priority(self) -> None:
        event = evaluate(self.message, ("укриття",), ("балістика на київ",))
        self.assertIsNotNone(event)
        self.assertEqual("critical", event.kind)

    def test_non_matching_message_has_no_event(self) -> None:
        message = TelegramMessage("test", "channel", "2", "Звичайне повідомлення", None, "")
        self.assertIsNone(evaluate(message, ("тривога",), ("балістика",)))

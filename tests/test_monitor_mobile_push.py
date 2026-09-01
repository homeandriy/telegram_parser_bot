from __future__ import annotations

from datetime import datetime, timezone
import unittest

from telegram_parser.config import ChannelConfig, Settings
from telegram_parser.models import TelegramMessage
from telegram_parser.monitor import Monitor
from telegram_parser.state import Resource


def settings() -> Settings:
    return Settings("postgresql://test", 10, 2, 180, "127.0.0.1", 8080, 0, "", "", "", "", (), (), (ChannelConfig("єРадар", "eRadarrua", "public"),))


class FakeStore:
    def __init__(self) -> None:
        self.created = True

    async def save_event(self, *_args: object) -> int | None:
        if not self.created:
            return None
        self.created = False
        return 42


class FakeDispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    async def dispatch(self, *args: object) -> int:
        self.calls.append(args)
        return 1


class MonitorMobilePushIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_new_match_dispatches_once_and_duplicate_event_does_not(self) -> None:
        monitor = Monitor(settings())
        monitor.store = FakeStore()  # type: ignore[assignment]
        dispatcher = FakeDispatcher()
        monitor.mobile_push = dispatcher  # type: ignore[assignment]
        message = TelegramMessage("public", "eRadarrua", "42", "Балістика на Київ", datetime.now(timezone.utc), "https://t.me/eRadarrua/42")
        resource = Resource("resource", "https://t.me/eRadarrua", "eRadarrua", "public", "єРадар")

        await monitor._handle_match(1, message, resource, "ballistics-kyiv", "Балістика на Київ", {}, ("Балістика", "Київ"))
        await monitor._handle_match(1, message, resource, "ballistics-kyiv", "Балістика на Київ", {}, ("Балістика", "Київ"))

        self.assertEqual(1, len(dispatcher.calls))
        self.assertEqual(42, dispatcher.calls[0][0])

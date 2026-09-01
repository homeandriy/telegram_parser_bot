from __future__ import annotations

from datetime import datetime, timezone
import unittest

import httpx

from telegram_parser.mobile_push import MobilePushDispatcher
from telegram_parser.models import AlertEvent, TelegramMessage


class FakeStore:
    def __init__(self, subscriptions: list[dict[str, object]]) -> None:
        self.subscriptions = subscriptions
        self.deliveries: dict[tuple[int, int], str | None] = {}

    async def list_mobile_subscriptions(self, event_id: int, resource_id: str, rule_id: str) -> list[dict[str, object]]:
        return [item for item in self.subscriptions if item["resource_id"] == resource_id and item["rule_id"] == rule_id and (event_id, int(item["device_id"])) not in self.deliveries]

    async def save_mobile_delivery(self, event_id: int, device_id: int, ticket_id: str | None) -> bool:
        key = (event_id, device_id)
        if key in self.deliveries:
            return False
        self.deliveries[key] = ticket_id
        return True


def event() -> AlertEvent:
    message = TelegramMessage("public", "eRadarrua", "42", "Балістика на Київ", datetime.now(timezone.utc), "https://t.me/eRadarrua/42")
    return AlertEvent(message, "rule:resource:ballistics-kyiv", "Балістика, Київ")


def client_factory(handler: httpx.AsyncBaseTransport):
    return lambda **_kwargs: httpx.AsyncClient(transport=handler)


class MobilePushDispatcherTest(unittest.IsolatedAsyncioTestCase):
    async def test_siren_payload_uses_siren_channel_and_sound(self) -> None:
        payloads: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payloads.append(__import__("json").loads(request.content))
            return httpx.Response(200, json={"data": [{"status": "ok", "id": "ticket-1"}]})

        store = FakeStore([{"device_id": 1, "expo_push_token": "ExpoPushToken[siren]", "sound": "siren", "resource_id": "resource", "rule_id": "ballistics-kyiv"}])
        dispatcher = MobilePushDispatcher(store, client_factory(httpx.MockTransport(handler)))  # type: ignore[arg-type]

        self.assertEqual(1, await dispatcher.dispatch(42, event(), "resource", "єРадар", "ballistics-kyiv", "Балістика на Київ"))
        self.assertEqual("siren.mp3", payloads[0]["sound"])
        self.assertEqual("air-alert-siren-v1", payloads[0]["channelId"])

    async def test_default_payload_uses_default_channel_and_sound(self) -> None:
        payloads: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payloads.append(__import__("json").loads(request.content))
            return httpx.Response(200, json={"data": [{"status": "ok", "id": "ticket-2"}]})

        store = FakeStore([{"device_id": 1, "expo_push_token": "ExpoPushToken[default]", "sound": "default", "resource_id": "resource", "rule_id": "ballistics-kyiv"}])
        dispatcher = MobilePushDispatcher(store, client_factory(httpx.MockTransport(handler)))  # type: ignore[arg-type]

        await dispatcher.dispatch(42, event(), "resource", "єРадар", "ballistics-kyiv", "Балістика на Київ")
        self.assertEqual("default", payloads[0]["sound"])
        self.assertEqual("air-alert-default-v1", payloads[0]["channelId"])

    async def test_unsubscribed_rule_does_not_send_push(self) -> None:
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={"data": [{"status": "ok", "id": "ticket"}]})

        store = FakeStore([{"device_id": 1, "expo_push_token": "ExpoPushToken[other]", "sound": "default", "resource_id": "resource", "rule_id": "shaheds-kyiv"}])
        dispatcher = MobilePushDispatcher(store, client_factory(httpx.MockTransport(handler)))  # type: ignore[arg-type]

        self.assertEqual(0, await dispatcher.dispatch(42, event(), "resource", "єРадар", "ballistics-kyiv", "Балістика на Київ"))
        self.assertEqual(0, calls)

    async def test_success_creates_one_delivery_with_ticket_and_is_idempotent(self) -> None:
        store = FakeStore([{"device_id": 1, "expo_push_token": "ExpoPushToken[one]", "sound": "default", "resource_id": "resource", "rule_id": "ballistics-kyiv"}])
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={"data": [{"status": "ok", "id": "ticket-3"}]})

        dispatcher = MobilePushDispatcher(store, client_factory(httpx.MockTransport(handler)))  # type: ignore[arg-type]

        await dispatcher.dispatch(42, event(), "resource", "єРадар", "ballistics-kyiv", "Балістика на Київ")
        await dispatcher.dispatch(42, event(), "resource", "єРадар", "ballistics-kyiv", "Балістика на Київ")
        self.assertEqual({(42, 1): "ticket-3"}, store.deliveries)
        self.assertEqual(1, calls)

    async def test_expo_errors_do_not_create_delivery_or_raise(self) -> None:
        store = FakeStore([{"device_id": 1, "expo_push_token": "ExpoPushToken[error]", "sound": "default", "resource_id": "resource", "rule_id": "ballistics-kyiv"}])
        dispatcher = MobilePushDispatcher(store, client_factory(httpx.MockTransport(lambda _request: httpx.Response(200, json={"data": [{"status": "error", "message": "bad token"}]}))))  # type: ignore[arg-type]

        self.assertEqual(0, await dispatcher.dispatch(42, event(), "resource", "єРадар", "ballistics-kyiv", "Балістика на Київ"))
        self.assertEqual({}, store.deliveries)

    async def test_expo_http_error_does_not_create_delivery_or_raise(self) -> None:
        store = FakeStore([{"device_id": 1, "expo_push_token": "ExpoPushToken[http-error]", "sound": "default", "resource_id": "resource", "rule_id": "ballistics-kyiv"}])
        dispatcher = MobilePushDispatcher(store, client_factory(httpx.MockTransport(lambda _request: httpx.Response(503))))  # type: ignore[arg-type]

        self.assertEqual(0, await dispatcher.dispatch(42, event(), "resource", "єРадар", "ballistics-kyiv", "Балістика на Київ"))
        self.assertEqual({}, store.deliveries)

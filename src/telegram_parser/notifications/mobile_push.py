"""Expo Push delivery for mobile Alert API subscribers."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

import httpx

from ..domain.models import AlertEvent
from ..infrastructure.storage import PostgresStore


logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_PUSH_TOKEN_PATTERN = re.compile(r"^(?:Expo|Exponent)PushToken\[[^\]\s]+\]$")
VALID_SOUNDS = frozenset({"default", "siren"})


def is_valid_expo_push_token(value: str) -> bool:
    """Return whether *value* is an Expo push token in a supported format."""
    return bool(EXPO_PUSH_TOKEN_PATTERN.fullmatch(value))


class MobilePushDispatcher:
    """Deliver a newly-created alert event to matching Expo device subscriptions."""

    def __init__(
        self,
        store: PostgresStore,
        client_factory: Callable[..., httpx.AsyncClient] | None = None,
    ) -> None:
        self.store = store
        self.client_factory = client_factory or httpx.AsyncClient

    async def dispatch(
        self,
        event_id: int,
        event: AlertEvent,
        resource_id: str,
        resource_name: str,
        rule_id: str,
        rule_title: str,
    ) -> int:
        """Send an event once per matching device and return successful deliveries."""
        deliveries = 0
        subscriptions = await self.store.list_mobile_subscriptions(event_id, resource_id, rule_id)
        for subscription in subscriptions:
            device_id = int(subscription["device_id"])
            try:
                payload = self._payload(event_id, event, resource_name, rule_id, rule_title, subscription)
                async with self.client_factory(timeout=10) as client:
                    response = await client.post(EXPO_PUSH_URL, json=payload)
                ticket_id = self._ticket_id(response)
                if ticket_id is _DELIVERY_FAILED:
                    logger.warning("Expo Push delivery failed for event_id=%s device_id=%s", event_id, device_id)
                    continue
                if await self.store.save_mobile_delivery(event_id, device_id, ticket_id):
                    deliveries += 1
            except Exception:
                logger.exception("Expo Push delivery failed for event_id=%s device_id=%s", event_id, device_id)
        return deliveries

    @staticmethod
    def _payload(
        event_id: int,
        event: AlertEvent,
        resource_name: str,
        rule_id: str,
        rule_title: str,
        subscription: dict[str, object],
    ) -> dict[str, object]:
        sound = str(subscription["sound"])
        if sound == "siren":
            expo_sound = "siren.mp3"
            channel_id = "air-alert-siren-v1"
        else:
            expo_sound = "default"
            channel_id = "air-alert-default-v1"
        return {
            "to": subscription["expo_push_token"],
            "title": f"{resource_name}: {rule_title}",
            "body": event.message.text,
            "priority": "high",
            "sound": expo_sound,
            "channelId": channel_id,
            "data": {
                "eventId": event_id,
                "ruleId": rule_id,
                "url": event.message.url,
            },
        }

    @staticmethod
    def _ticket_id(response: httpx.Response) -> str | None | object:
        if not response.is_success:
            return _DELIVERY_FAILED
        try:
            body: Any = response.json()
            item = body["data"][0]
        except (IndexError, KeyError, TypeError, ValueError):
            return _DELIVERY_FAILED
        if item.get("status") != "ok":
            return _DELIVERY_FAILED
        ticket_id = item.get("id")
        return str(ticket_id) if ticket_id is not None else None


_DELIVERY_FAILED = object()

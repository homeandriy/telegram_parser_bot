"""Signed webhook delivery for the future mobile alarm receiver."""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx

from ..domain.models import AlertEvent


class WebhookNotifier:
    def __init__(self, endpoint: str, secret: str) -> None:
        self.endpoint = endpoint
        self.secret = secret

    async def deliver(self, event_id: int, event: AlertEvent) -> bool:
        if not self.endpoint or not self.secret:
            return False
        payload = json.dumps(
            {
                "event_id": event_id,
                "kind": event.kind,
                "channel": event.message.channel,
                "text": event.message.text,
                "url": event.message.url,
                "matched_pattern": event.matched_pattern,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        signature = hmac.new(self.secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                self.endpoint,
                content=payload,
                headers={"Content-Type": "application/json", "X-Telegram-Alert-Signature": signature, "Idempotency-Key": str(event_id)},
            )
        return response.is_success

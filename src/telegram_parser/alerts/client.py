"""alerts.in.ua active-air-raid API client."""

from __future__ import annotations

import logging
from collections.abc import Mapping

import httpx

from ..core.runtime import ALERTS_IN_UA_ACTIVE_URL, ALERTS_IN_UA_TIMEOUT_SECONDS


logger = logging.getLogger(__name__)

def active_air_raid_location_uids(payload: Mapping[str, object]) -> frozenset[str]:
    """Return all region UIDs covered by active air-raid alerts."""
    raw_alerts = payload.get("alerts", [])
    if not isinstance(raw_alerts, list):
        return frozenset()
    location_uids: set[str] = set()
    for item in raw_alerts:
        if not isinstance(item, Mapping) or item.get("alert_type") != "air_raid":
            continue
        if item.get("finished_at") is not None:
            continue
        for key in ("location_uid", "location_oblast_uid"):
            value = str(item.get(key, "")).strip()
            if value:
                location_uids.add(value)
    return frozenset(location_uids)


class AlertsInUaClient:
    """Fetch active alerts through one authenticated request per poll."""

    def __init__(self, token: str) -> None:
        self.token = token.strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.token)

    async def active_air_raid_location_uids(self) -> frozenset[str]:
        if not self.is_configured:
            return frozenset()
        try:
            async with httpx.AsyncClient(timeout=ALERTS_IN_UA_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    ALERTS_IN_UA_ACTIVE_URL,
                    headers={"Authorization": f"Bearer {self.token}"},
                )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, Mapping):
                raise ValueError("alerts.in.ua returned a non-object JSON response")
            return active_air_raid_location_uids(payload)
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("alerts.in.ua active-alerts request failed: %s", error)
            raise

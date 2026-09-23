"""alerts.in.ua active-air-raid API client."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from ..core.runtime import ALERTS_IN_UA_ACTIVE_URL, ALERTS_IN_UA_TIMEOUT_SECONDS


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActiveAirRaidAlert:
    """Public map data for one active air-raid alert."""

    id: int | str | None
    location_uid: str
    location_title: str | None
    location_type: str | None
    location_oblast_uid: str | None
    location_oblast: str | None
    started_at: str | None
    updated_at: str | None


@dataclass(frozen=True)
class ActiveAirRaidSnapshot:
    """Latest successfully retrieved active-air-raid snapshot."""

    updated_at: datetime | None = None
    alerts: tuple[ActiveAirRaidAlert, ...] = ()


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def active_air_raid_alerts(payload: Mapping[str, object]) -> tuple[ActiveAirRaidAlert, ...]:
    """Normalize every active air-raid alert for clients that render a map."""
    raw_alerts = payload.get("alerts", [])
    if not isinstance(raw_alerts, list):
        return ()
    alerts: list[ActiveAirRaidAlert] = []
    for item in raw_alerts:
        if not isinstance(item, Mapping) or item.get("alert_type") != "air_raid":
            continue
        if item.get("finished_at") is not None:
            continue
        location_uid = str(item.get("location_uid", "")).strip()
        if not location_uid:
            continue
        raw_id = item.get("id")
        alerts.append(
            ActiveAirRaidAlert(
                id=raw_id if isinstance(raw_id, (int, str)) else None,
                location_uid=location_uid,
                location_title=_optional_text(item.get("location_title")),
                location_type=_optional_text(item.get("location_type")),
                location_oblast_uid=_optional_text(item.get("location_oblast_uid")),
                location_oblast=_optional_text(item.get("location_oblast")),
                started_at=_optional_text(item.get("started_at")),
                updated_at=_optional_text(item.get("updated_at")),
            )
        )
    return tuple(alerts)

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
        self._snapshot = ActiveAirRaidSnapshot()

    @property
    def is_configured(self) -> bool:
        return bool(self.token)

    async def active_air_raid_location_uids(self) -> frozenset[str]:
        snapshot = await self.refresh_active_air_raid_alerts()
        return frozenset(
            uid
            for alert in snapshot.alerts
            for uid in (alert.location_uid, alert.location_oblast_uid)
            if uid
        )

    def active_air_raid_snapshot(self) -> ActiveAirRaidSnapshot:
        """Return the cached result without making another upstream request."""
        return self._snapshot

    async def refresh_active_air_raid_alerts(self) -> ActiveAirRaidSnapshot:
        """Refresh the shared snapshot used by the monitor and public API."""
        if not self.is_configured:
            return self._snapshot
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
            self._snapshot = ActiveAirRaidSnapshot(
                updated_at=datetime.now(timezone.utc),
                alerts=active_air_raid_alerts(payload),
            )
            return self._snapshot
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("alerts.in.ua active-alerts request failed: %s", error)
            raise

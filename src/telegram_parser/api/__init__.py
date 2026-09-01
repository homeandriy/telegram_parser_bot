"""HTTP API for the durable Telegram alert event pool."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator, Callable

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from ..core.config import Settings
from ..notifications.mobile_push import VALID_SOUNDS, is_valid_expo_push_token
from ..domain.rules import describe_scenarios
from ..desktop.state import Resource, StateRepository
from ..infrastructure.storage import PostgresStore


def _timestamp(value: object) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _event_payload(event: dict[str, object]) -> dict[str, object]:
    return {
        "id": event["id"],
        "idempotency_key": event["idempotency_key"],
        "resource": {
            "id": event["resource_id"],
            "name": event["resource_name"],
            "channel": event["channel"],
            "source": event["source"],
        },
        "rule": {
            "id": event["rule_id"] or event["rule_reference"],
            "title": event["rule_title"] or event["rule_reference"],
        },
        "reason": event["reason"],
        "message": {
            "external_id": event["external_id"],
            "text": event["body"],
            "url": event["url"],
            "published_at": _timestamp(event["published_at"]),
        },
        "created_at": _timestamp(event["created_at"]),
        "acknowledged_at": _timestamp(event["delivered_at"]),
    }



async def _resource_location(store: PostgresStore, resource: Resource) -> dict[str, object] | None:
    """Resolve the optional rayon UID selected for a channel."""
    raw_uid = resource.location_uid.strip()
    if not raw_uid:
        return None
    if raw_uid.isdecimal():
        location = await store.get_location(int(raw_uid))
        if location is not None:
            return location
    return {"uid": raw_uid, "title": None, "location_type": None, "oblast": None}

class MobileDevicePreference(BaseModel):
    enabled: bool = True
    sound: str = "default"


class MobileDeviceRegistration(BaseModel):
    expoPushToken: str = Field(min_length=1)
    preferences: dict[str, MobileDevicePreference]


def _available_rule_keys(state: StateRepository) -> set[str]:
    configured_rules = state.load_rules()
    return {
        f"{resource.id}:{descriptor.id}"
        for resource in state.load_resources()
        for descriptor in describe_scenarios(configured_rules.get(resource.id, {}))
    }


def create_app(
    settings: Settings,
    state: StateRepository,
    store_factory: Callable[[str], PostgresStore] = PostgresStore,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = store_factory(settings.database_dsn)
        await store.connect()
        app.state.store = store
        try:
            yield
        finally:
            await store.close()

    app = FastAPI(title="Telegram Alert API", version="0.5.0", lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.get("/api/health")
    async def health() -> dict[str, object]:
        status = await app.state.store.status()
        return {
            "last_checked_at": _timestamp(status["last_checked_at"]),
            "last_successful_at": _timestamp(status["last_successful_at"]),
            "pending_events": status["pending_events"],
        }

    @app.get("/api/events")
    async def events(
        limit: int = Query(default=100, ge=1, le=500),
        include_delivered: bool = False,
        subscription: list[str] = Query(default=[]),
    ) -> dict[str, object]:
        subscriptions: list[tuple[str, str]] = []
        for value in subscription:
            try:
                resource_id, rule_id = value.split(":", 1)
            except ValueError as error:
                raise HTTPException(status_code=422, detail="subscription must be resource_id:rule_id") from error
            subscriptions.append((resource_id, rule_id))
        status = await app.state.store.status()
        stored_events = await app.state.store.list_events(limit, include_delivered, subscriptions)
        return {
            "last_checked_at": _timestamp(status["last_checked_at"]),
            "events": [_event_payload(event) for event in stored_events],
        }

    @app.get("/api/rules")
    async def rules() -> dict[str, object]:
        configured_rules = state.load_rules()
        channels = []
        for resource in state.load_resources():
            channels.append(
                {
                    "id": resource.id,
                    "name": resource.name,
                    "username": resource.username,
                    "location": await _resource_location(app.state.store, resource),
                    "rules": [descriptor.__dict__ for descriptor in describe_scenarios(configured_rules.get(resource.id, {}))],
                }
            )
        return {"channels": channels}

    @app.get("/api/locations/regions")
    async def location_regions() -> dict[str, object]:
        return {"locations": await app.state.store.list_location_regions()}

    @app.get("/api/locations/regions/{region_uid}/raions")
    async def location_raions(region_uid: int) -> dict[str, object]:
        return {"locations": await app.state.store.list_location_raions(region_uid)}

    @app.post("/api/mobile-devices")
    async def register_mobile_device(registration: MobileDeviceRegistration) -> dict[str, int | bool]:
        if not is_valid_expo_push_token(registration.expoPushToken):
            raise HTTPException(status_code=422, detail="expoPushToken must be a valid Expo push token")
        available_rule_keys = _available_rule_keys(state)
        subscriptions: list[tuple[str, str, str]] = []
        for key, preference in registration.preferences.items():
            if key not in available_rule_keys:
                raise HTTPException(status_code=422, detail=f"Unknown rule: {key}")
            if preference.sound not in VALID_SOUNDS:
                raise HTTPException(status_code=422, detail="sound must be default or siren")
            if preference.enabled:
                resource_id, rule_id = key.split(":", 1)
                subscriptions.append((resource_id, rule_id, preference.sound))
        device_id, count = await app.state.store.register_mobile_device(registration.expoPushToken, subscriptions)
        return {"registered": True, "device_id": device_id, "subscriptions": count}

    @app.post("/api/events/{event_id}/ack")
    async def acknowledge(event_id: int) -> dict[str, bool]:
        if event_id < 1 or not await app.state.store.mark_delivered(event_id):
            raise HTTPException(status_code=404, detail="Event not found")
        return {"acknowledged": True}

    return app


async def serve_api(settings: Settings, state: StateRepository) -> None:
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings, state),
            host=settings.api_host,
            port=settings.api_port,
            log_level="info",
            access_log=False,
        )
    )
    await server.serve()

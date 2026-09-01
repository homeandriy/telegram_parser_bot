"""Adaptive polling loop and one-off synchronization."""

from __future__ import annotations

import asyncio
import json
import logging
from time import monotonic

import httpx
from ..alerts.client import AlertsInUaClient
from ..core.config import ChannelConfig, Settings
from ..notifications.mobile_push import MobilePushDispatcher
from ..notifications.webhook import WebhookNotifier
from ..core.runtime import ACTIVE_ALERT_CHANNEL_POLL_SECONDS, ALERTS_IN_UA_POLL_SECONDS, CHANNEL_MESSAGE_LIMIT, NORMAL_CHANNEL_POLL_SECONDS, OUTBOUND_ACTION_TIMEOUT_SECONDS
from ..domain.rules import describe_scenarios, evaluate_scenarios
from ..infrastructure.sources import PublicPreviewSource, TelethonSource
from ..desktop.state import Resource, StateRepository
from ..infrastructure.storage import PostgresStore


logger = logging.getLogger(__name__)


class Monitor:
    def __init__(self, settings: Settings, state: StateRepository | None = None) -> None:
        self.settings = settings
        self.store = PostgresStore(settings.database_dsn)
        self.notifier = WebhookNotifier(settings.notifier_endpoint, settings.notifier_secret)
        self.mobile_push = MobilePushDispatcher(self.store)
        self.alerts = AlertsInUaClient(settings.alerts_in_ua_token)
        self.active_location_uids: frozenset[str] = frozenset()
        self.state = state

    async def sync_once(self) -> int:
        await self.store.connect()
        try:
            try:
                created = await self._sync_channels()
            except Exception:
                await self.store.record_check(False)
                raise
            await self.store.record_check(True)
            return created
        finally:
            await self.store.close()

    async def daemon(self) -> None:
        await self.store.connect()
        next_alert_poll = 0.0 if self.alerts.is_configured else float("inf")
        next_resource_poll: dict[str, float] = {}
        if not self.alerts.is_configured:
            logger.warning("ALERTS_IN_UA_TOKEN is not set; Telegram channels will use the normal interval")
        try:
            while True:
                now = monotonic()
                if self.alerts.is_configured and now >= next_alert_poll:
                    try:
                        self.active_location_uids = await self.alerts.active_air_raid_location_uids()
                    except Exception:
                        logger.exception("alerts.in.ua synchronization failed; retaining the previous alert state")
                    next_alert_poll = monotonic() + ALERTS_IN_UA_POLL_SECONDS
                resources, rules = self._resources_and_rules()
                active_resource_ids = {resource.id for resource in resources}
                for resource_id in tuple(next_resource_poll):
                    if resource_id not in active_resource_ids:
                        del next_resource_poll[resource_id]
                for resource in resources:
                    if now < next_resource_poll.get(resource.id, 0.0):
                        continue
                    try:
                        await self._sync_resource(resource, rules.get(resource.id, {}))
                    except Exception:
                        logger.exception("Telegram synchronization failed for resource=%s", resource.id)
                        await self.store.record_check(False)
                    else:
                        await self.store.record_check(True)
                    interval = ACTIVE_ALERT_CHANNEL_POLL_SECONDS if self._rule_location_uids(rules.get(resource.id, {})) & self.active_location_uids else NORMAL_CHANNEL_POLL_SECONDS
                    next_resource_poll[resource.id] = monotonic() + interval
                next_due = min([next_alert_poll, *next_resource_poll.values()]) if next_resource_poll else next_alert_poll
                await asyncio.sleep(max(0.1, next_due - monotonic()))
        finally:
            await self.store.close()

    def _resources_and_rules(self) -> tuple[list[Resource], dict[str, dict]]:
        if self.state is None:
            resources = [
                Resource(channel.username, f"https://t.me/{channel.username}", channel.username, channel.source, channel.name)
                for channel in self.settings.channels
            ]
            return resources, {}
        return self.state.load_resources(), self.state.load_rules()
    @staticmethod
    def _rule_location_uids(rule: dict) -> frozenset[str]:
        return frozenset(descriptor.location_uid for descriptor in describe_scenarios(rule))
    async def _sync_channels(self) -> int:
        created = 0
        resources, rules = self._resources_and_rules()
        for resource in resources:
            created += await self._sync_resource(resource, rules.get(resource.id, {}))
        return created
    async def _sync_resource(self, resource: Resource, rule: dict) -> int:
        channel = ChannelConfig(resource.name, resource.username, resource.sync_type)
        source = TelethonSource(self.settings, CHANNEL_MESSAGE_LIMIT) if channel.source == "telethon" else PublicPreviewSource(CHANNEL_MESSAGE_LIMIT)
        created = 0
        for message in await source.fetch(channel):
            message_id = await self.store.save_message(message)
            if message_id is None:
                continue
            created += 1
            for match in evaluate_scenarios(message, rule):
                await self._handle_match(message_id, message, resource, match.rule_id, match.rule_title, match.action, match.matched_terms)
        return created

    async def _handle_match(
        self,
        message_id: int,
        message,
        resource: Resource,
        rule_id: str,
        rule_title: str,
        action: dict,
        terms: tuple[str, ...],
    ) -> None:
        from ..domain.models import AlertEvent

        event = AlertEvent(message, f"rule:{resource.id}:{rule_id}", ", ".join(terms))
        event_id = await self.store.save_event(message_id, event, resource.id, resource.name, rule_id, rule_title)
        if event_id is None:
            return
        try:
            await self.mobile_push.dispatch(event_id, event, resource.id, resource.name, rule_id, rule_title)
        except Exception:
            logger.exception("Mobile Push dispatch failed for event_id=%s", event_id)
        action_result = await self._execute_action(action, event_id, event)
        if self.state:
            self.state.append_event({"resource_id": resource.id, "resource": resource.name, "rule_id": rule_id, "rule_title": rule_title, "matched": list(terms), "message": message.text, "url": message.url, "action": action_result})

    async def _execute_action(self, action: dict, event_id: int, event) -> str:
        url = str(action.get("url", "")).strip()
        if not url:
            return "Збіг зафіксовано; HTTP-дія не налаштована."
        try:
            headers = json.loads(action.get("headers", "{}"))
            body = json.loads(action.get("body", "{}"))
            async with httpx.AsyncClient(timeout=OUTBOUND_ACTION_TIMEOUT_SECONDS) as client:
                response = await (client.get(url, headers=headers, params=body) if action.get("method") == "GET" else client.post(url, headers=headers, json=body))
            if response.is_success:
                await self.store.mark_delivered(event_id)
                return f"{action.get('method', 'POST')} {url}: {response.status_code}"
            return f"{action.get('method', 'POST')} {url}: HTTP {response.status_code}"
        except Exception as error:
            return f"Помилка HTTP-дії: {error}"


def run_sync(settings: Settings) -> int:
    return asyncio.run(Monitor(settings).sync_once())


async def preview_sync(settings: Settings) -> str:
    """Fetch configured sources for the desktop UI without requiring a server database."""
    results: list[str] = []
    for channel in settings.channels:
        source = TelethonSource(settings) if channel.source == "telethon" else PublicPreviewSource()
        messages = await source.fetch(channel)
        results.append(f"{channel.name}: {len(messages)}")
    return "; ".join(results)


def run_preview_sync(settings: Settings) -> str:
    return asyncio.run(preview_sync(settings))


def run_daemon(settings: Settings, state: StateRepository | None = None) -> None:
    from ..api import serve_api

    async def run_services() -> None:
        await asyncio.gather(Monitor(settings, state).daemon(), serve_api(settings, state))

    asyncio.run(run_services())

"""PostgreSQL storage with idempotent message and event writes."""

from __future__ import annotations

from hashlib import sha256
from datetime import datetime, timezone

import asyncpg

from .models import AlertEvent, TelegramMessage


EVENT_RETENTION_LIMIT = 5_000


def event_idempotency_key(message: TelegramMessage, rule_reference: str) -> str:
    """Return a stable key for one rule matching one Telegram message."""
    payload = "\x1f".join((message.source, message.channel, message.external_id, rule_reference))
    return sha256(payload.encode("utf-8")).hexdigest()


class PostgresStore:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=4)
        async with self.pool.acquire() as connection:
            await connection.execute("SELECT pg_advisory_lock(4508080)")
            try:
                await connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS telegram_messages (
                        id BIGSERIAL PRIMARY KEY,
                        source TEXT NOT NULL,
                        channel TEXT NOT NULL,
                        external_id TEXT NOT NULL,
                        body TEXT NOT NULL,
                        published_at TIMESTAMPTZ,
                        url TEXT NOT NULL,
                        received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        UNIQUE (source, channel, external_id)
                    );
                    CREATE TABLE IF NOT EXISTS alert_events (
                        id BIGSERIAL PRIMARY KEY,
                        message_id BIGINT NOT NULL REFERENCES telegram_messages(id),
                        kind TEXT NOT NULL,
                        matched_pattern TEXT NOT NULL,
                    resource_id TEXT,
                    resource_name TEXT,
                    rule_id TEXT,
                    rule_title TEXT,
                    idempotency_key TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        delivered_at TIMESTAMPTZ,
                        UNIQUE (message_id, kind)
                    );
                    CREATE TABLE IF NOT EXISTS monitor_status (
                        singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
                        last_checked_at TIMESTAMPTZ,
                        last_successful_at TIMESTAMPTZ
                    );
                    CREATE TABLE IF NOT EXISTS mobile_devices (
                        id BIGSERIAL PRIMARY KEY,
                        expo_push_token TEXT NOT NULL UNIQUE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    CREATE TABLE IF NOT EXISTS mobile_device_subscriptions (
                        device_id BIGINT NOT NULL REFERENCES mobile_devices(id) ON DELETE CASCADE,
                        resource_id TEXT NOT NULL,
                        rule_id TEXT NOT NULL,
                        sound TEXT NOT NULL CHECK (sound IN ('default', 'siren')),
                        UNIQUE (device_id, resource_id, rule_id)
                    );
                    CREATE TABLE IF NOT EXISTS mobile_alert_deliveries (
                        event_id BIGINT NOT NULL REFERENCES alert_events(id) ON DELETE CASCADE,
                        device_id BIGINT NOT NULL REFERENCES mobile_devices(id) ON DELETE CASCADE,
                        expo_ticket_id TEXT,
                        sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        UNIQUE (event_id, device_id)
                    );
                    INSERT INTO monitor_status (singleton) VALUES (TRUE) ON CONFLICT (singleton) DO NOTHING;
                    """
                )
                await connection.execute(
                    """
                ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS resource_id TEXT;
                ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS resource_name TEXT;
                ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS rule_id TEXT;
                ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS rule_title TEXT;
                ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS idempotency_key TEXT;
                    """
                )
            finally:
                await connection.execute("SELECT pg_advisory_unlock(4508080)")

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()

    async def save_message(self, message: TelegramMessage) -> int | None:
        if self.pool is None:
            raise RuntimeError("Store is not connected")
        published_at = message.published_at or datetime.now(timezone.utc)
        async with self.pool.acquire() as connection:
            return await connection.fetchval(
                """
                INSERT INTO telegram_messages (source, channel, external_id, body, published_at, url)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (source, channel, external_id) DO NOTHING
                RETURNING id
                """,
                message.source,
                message.channel,
                message.external_id,
                message.text,
                published_at,
                message.url,
            )

    async def save_event(
        self,
        message_id: int,
        event: AlertEvent,
        resource_id: str,
        resource_name: str,
        rule_id: str,
        rule_title: str,
    ) -> int | None:
        if self.pool is None:
            raise RuntimeError("Store is not connected")
        idempotency_key = event_idempotency_key(event.message, event.kind)
        async with self.pool.acquire() as connection:
            event_id = await connection.fetchval(
                """
                INSERT INTO alert_events (message_id, kind, matched_pattern, resource_id, resource_name, rule_id, rule_title, idempotency_key)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (message_id, kind) DO NOTHING
                RETURNING id
                """,
                message_id,
                event.kind,
                event.matched_pattern,
                resource_id,
                resource_name,
                rule_id,
                rule_title,
                idempotency_key,
            )
            if event_id is not None:
                await connection.execute(
                    """
                    DELETE FROM alert_events
                    WHERE id IN (
                        SELECT id
                        FROM alert_events
                        ORDER BY created_at DESC, id DESC
                        OFFSET $1
                    )
                    """,
                    EVENT_RETENTION_LIMIT,
                )
            return event_id

    async def register_mobile_device(
        self,
        expo_push_token: str,
        subscriptions: list[tuple[str, str, str]],
    ) -> tuple[int, int]:
        """Replace all device subscriptions atomically and return its id and count."""
        if self.pool is None:
            raise RuntimeError("Store is not connected")
        async with self.pool.acquire() as connection, connection.transaction():
            device_id = await connection.fetchval(
                """
                INSERT INTO mobile_devices (expo_push_token)
                VALUES ($1)
                ON CONFLICT (expo_push_token) DO UPDATE SET updated_at = now()
                RETURNING id
                """,
                expo_push_token,
            )
            await connection.execute("DELETE FROM mobile_device_subscriptions WHERE device_id = $1", device_id)
            if subscriptions:
                await connection.executemany(
                    """
                    INSERT INTO mobile_device_subscriptions (device_id, resource_id, rule_id, sound)
                    VALUES ($1, $2, $3, $4)
                    """,
                    [(device_id, resource_id, rule_id, sound) for resource_id, rule_id, sound in subscriptions],
                )
        return int(device_id), len(subscriptions)

    async def list_mobile_subscriptions(self, event_id: int, resource_id: str, rule_id: str) -> list[dict[str, object]]:
        """Return subscribed devices that have not already received this event."""
        if self.pool is None:
            raise RuntimeError("Store is not connected")
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT mobile_devices.id AS device_id, mobile_devices.expo_push_token, mobile_device_subscriptions.sound
                FROM mobile_device_subscriptions
                INNER JOIN mobile_devices ON mobile_devices.id = mobile_device_subscriptions.device_id
                LEFT JOIN mobile_alert_deliveries
                    ON mobile_alert_deliveries.device_id = mobile_devices.id
                    AND mobile_alert_deliveries.event_id = $1
                WHERE mobile_device_subscriptions.resource_id = $2
                    AND mobile_device_subscriptions.rule_id = $3
                    AND mobile_alert_deliveries.event_id IS NULL
                """,
                event_id,
                resource_id,
                rule_id,
            )
        return [dict(row) for row in rows]

    async def save_mobile_delivery(self, event_id: int, device_id: int, expo_ticket_id: str | None) -> bool:
        """Persist a successful Expo delivery without duplicating an event/device pair."""
        if self.pool is None:
            raise RuntimeError("Store is not connected")
        async with self.pool.acquire() as connection:
            result = await connection.execute(
                """
                INSERT INTO mobile_alert_deliveries (event_id, device_id, expo_ticket_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (event_id, device_id) DO NOTHING
                """,
                event_id,
                device_id,
                expo_ticket_id,
            )
        return result == "INSERT 0 1"

    async def mark_delivered(self, event_id: int) -> bool:
        if self.pool is None:
            raise RuntimeError("Store is not connected")
        async with self.pool.acquire() as connection:
            result = await connection.execute("UPDATE alert_events SET delivered_at = now() WHERE id = $1", event_id)
        return result == "UPDATE 1"

    async def record_check(self, successful: bool) -> None:
        if self.pool is None:
            raise RuntimeError("Store is not connected")
        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                UPDATE monitor_status
                SET last_checked_at = now(),
                    last_successful_at = CASE WHEN $1 THEN now() ELSE last_successful_at END
                WHERE singleton = TRUE
                """,
                successful,
            )

    async def status(self) -> dict[str, datetime | int | None]:
        if self.pool is None:
            raise RuntimeError("Store is not connected")
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    monitor_status.last_checked_at,
                    monitor_status.last_successful_at,
                    COUNT(alert_events.id) FILTER (WHERE alert_events.delivered_at IS NULL) AS pending_events
                FROM monitor_status
                LEFT JOIN alert_events ON TRUE
                WHERE monitor_status.singleton = TRUE
                GROUP BY monitor_status.last_checked_at, monitor_status.last_successful_at
                """
            )
        return dict(row) if row is not None else {"last_checked_at": None, "last_successful_at": None, "pending_events": 0}

    async def list_events(
        self,
        limit: int,
        include_delivered: bool,
        subscriptions: list[tuple[str, str]] | None = None,
    ) -> list[dict[str, object]]:
        if self.pool is None:
            raise RuntimeError("Store is not connected")
        filters = ["TRUE" if include_delivered else "alert_events.delivered_at IS NULL"]
        arguments: list[object] = [limit]
        if subscriptions:
            subscription_filters: list[str] = []
            for resource_id, rule_id in subscriptions:
                resource_position = len(arguments) + 1
                arguments.append(resource_id)
                rule_position = len(arguments) + 1
                arguments.append(rule_id)
                subscription_filters.append(f"(alert_events.resource_id = ${resource_position} AND alert_events.rule_id = ${rule_position})")
            filters.append("(" + " OR ".join(subscription_filters) + ")")
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                f"""
                SELECT
                    alert_events.id,
                    alert_events.idempotency_key,
                    alert_events.kind AS rule_reference,
                    alert_events.matched_pattern AS reason,
                    alert_events.resource_id,
                    alert_events.resource_name,
                    alert_events.rule_id,
                    alert_events.rule_title,
                    alert_events.created_at,
                    alert_events.delivered_at,
                    telegram_messages.source,
                    telegram_messages.channel,
                    telegram_messages.external_id,
                    telegram_messages.body,
                    telegram_messages.published_at,
                    telegram_messages.url
                FROM alert_events
                INNER JOIN telegram_messages ON telegram_messages.id = alert_events.message_id
                WHERE {' AND '.join(filters)}
                ORDER BY alert_events.created_at DESC, alert_events.id DESC
                LIMIT $1
                """,
                *arguments,
            )
        return [dict(row) for row in rows]

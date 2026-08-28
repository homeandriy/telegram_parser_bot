"""PostgreSQL storage with idempotent message and event writes."""

from __future__ import annotations

from datetime import datetime, timezone

import asyncpg

from .models import AlertEvent, TelegramMessage


class PostgresStore:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=4)
        async with self.pool.acquire() as connection:
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
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    delivered_at TIMESTAMPTZ,
                    UNIQUE (message_id, kind)
                );
                """
            )

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

    async def save_event(self, message_id: int, event: AlertEvent) -> int | None:
        if self.pool is None:
            raise RuntimeError("Store is not connected")
        async with self.pool.acquire() as connection:
            return await connection.fetchval(
                """
                INSERT INTO alert_events (message_id, kind, matched_pattern)
                VALUES ($1, $2, $3)
                ON CONFLICT (message_id, kind) DO NOTHING
                RETURNING id
                """,
                message_id,
                event.kind,
                event.matched_pattern,
            )

    async def mark_delivered(self, event_id: int) -> None:
        if self.pool is None:
            raise RuntimeError("Store is not connected")
        async with self.pool.acquire() as connection:
            await connection.execute("UPDATE alert_events SET delivered_at = now() WHERE id = $1", event_id)

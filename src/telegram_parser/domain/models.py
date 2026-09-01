"""Domain models shared by the UI and daemon."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TelegramMessage:
    source: str
    channel: str
    external_id: str
    text: str
    published_at: datetime | None
    url: str
    media_urls: tuple[str, ...] = ()
    video_urls: tuple[str, ...] = ()


@dataclass(frozen=True)
class AlertEvent:
    message: TelegramMessage
    kind: str
    matched_pattern: str

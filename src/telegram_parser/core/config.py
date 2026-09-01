"""Typed configuration loaded from a local TOML file."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .runtime import ACTIVE_ALERT_CHANNEL_POLL_SECONDS, NORMAL_CHANNEL_POLL_SECONDS


@dataclass(frozen=True)
class ChannelConfig:
    name: str
    username: str
    source: str


@dataclass(frozen=True)
class Settings:
    database_dsn: str
    normal_seconds: int
    alert_seconds: int
    alert_mode_minutes: int
    api_host: str
    api_port: int
    api_id: int
    api_hash: str
    session_path: str
    notifier_endpoint: str
    notifier_secret: str
    escalation_patterns: tuple[str, ...]
    critical_patterns: tuple[str, ...]
    channels: tuple[ChannelConfig, ...]
    alerts_in_ua_token: str = ""


def load_settings(path: Path) -> Settings:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    database = data.get("database", {})
    polling = data.get("polling", {})
    api = data.get("api", {})
    telethon = data.get("telethon", {})
    notifier = data.get("notifier", {})
    rules = data.get("rules", {})
    channels = tuple(
        ChannelConfig(
            name=str(item.get("name", item.get("username", ""))),
            username=str(item["username"]).lstrip("@").removeprefix("https://t.me/s/").removeprefix("https://t.me/"),
            source=str(item.get("source", "public")),
        )
        for item in data.get("channels", [])
    )
    if not database.get("dsn"):
        raise ValueError("database.dsn is required")
    if not channels:
        raise ValueError("Add at least one [[channels]] entry")
    invalid = [channel.source for channel in channels if channel.source not in {"telethon", "public"}]
    if invalid:
        raise ValueError(f"Unknown channel source: {invalid[0]}")
    return Settings(
        database_dsn=str(database["dsn"]),
        normal_seconds=NORMAL_CHANNEL_POLL_SECONDS,
        alert_seconds=ACTIVE_ALERT_CHANNEL_POLL_SECONDS,
        alert_mode_minutes=max(1, int(polling.get("alert_mode_minutes", 180))),
        api_host=str(api.get("host", "127.0.0.1")),
        api_port=max(1, min(65535, int(api.get("port", 8080)))),
        api_id=int(telethon.get("api_id", 0)),
        api_hash=str(telethon.get("api_hash", "")),
        session_path=str(telethon.get("session_path", "telegram-monitor.session")),
        notifier_endpoint=str(notifier.get("endpoint", "")),
        notifier_secret=str(notifier.get("secret", "")),
        escalation_patterns=tuple(str(value) for value in rules.get("escalation_patterns", [])),
        critical_patterns=tuple(str(value) for value in rules.get("critical_patterns", [])),
        channels=channels,
        alerts_in_ua_token=os.environ.get("ALERTS_IN_UA_TOKEN", ""),
    )

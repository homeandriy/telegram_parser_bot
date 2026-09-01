"""Portable user-editable configuration files for the desktop application."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


@dataclass
class Resource:
    id: str
    url: str
    username: str
    sync_type: str
    name: str
    description: str = ""
    location_uid: str = ""


DEFAULT_RESOURCES = (
    ("https://t.me/eRadarrua", "eRadarrua", "єРадар"),
    ("https://t.me/insiderUKR", "insiderUKR", "INSIDER UA"),
    ("https://t.me/vanek_nikolaev", "vanek_nikolaev", "Vanek Nikolaev"),
)


def default_state_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "config"
    return Path.cwd() / "config"


class StateRepository:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or default_state_dir()
        self.resources_path = self.directory / "resources.json"
        self.rules_path = self.directory / "rules.json"
        self.settings_path = self.directory / "settings.toml"
        self.events_path = self.directory / "events.json"
        self.directory.mkdir(parents=True, exist_ok=True)

    def load_resources(self) -> list[Resource]:
        if not self.resources_path.exists():
            resources = [Resource(str(uuid4()), url, username, "public", name) for url, username, name in DEFAULT_RESOURCES]
            self.save_resources(resources)
            return resources
        raw = json.loads(self.resources_path.read_text(encoding="utf-8"))
        return [Resource(**{key: value for key, value in item.items() if key != "region_name"}) for item in raw]

    def save_resources(self, resources: list[Resource]) -> None:
        self.resources_path.write_text(json.dumps([asdict(resource) for resource in resources], ensure_ascii=False, indent=2), encoding="utf-8")

    def load_rules(self) -> dict[str, dict]:
        if not self.rules_path.exists():
            return {}
        return json.loads(self.rules_path.read_text(encoding="utf-8"))

    def save_rules(self, rules: dict[str, dict]) -> None:
        self.rules_path.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_events(self) -> list[dict]:
        if not self.events_path.exists():
            return []
        try:
            return json.loads(self.events_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

    def append_event(self, event: dict) -> None:
        events = self.load_events()
        event.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        events.insert(0, event)
        self.events_path.write_text(json.dumps(events[:1000], ensure_ascii=False, indent=2), encoding="utf-8")

    def load_settings(self) -> dict[str, str | int]:
        if not self.settings_path.exists():
            settings: dict[str, str | int] = {
                "api_port": 4557,
                "language": "uk",
                "telethon_api_id": "",
                "telethon_api_hash": "",
                "telethon_phone": "",
                "telethon_session_path": str(self.directory / "telegram-monitor.session"),
            }
            self.save_settings(settings)
            return settings
        values: dict[str, str | int] = {}
        for line in self.settings_path.read_text(encoding="utf-8").splitlines():
            if "=" not in line:
                continue
            key, value = (part.strip() for part in line.split("=", 1))
            values[key] = int(value) if value.isdigit() else value.strip('"')
        return {
            "api_port": int(values.get("api_port", 4557)),
            "language": str(values.get("language", "uk")),
            "telethon_api_id": str(values.get("telethon_api_id", "")),
            "telethon_api_hash": str(values.get("telethon_api_hash", "")),
            "telethon_phone": str(values.get("telethon_phone", "")),
            "telethon_session_path": str(values.get("telethon_session_path", self.directory / "telegram-monitor.session")),
        }

    def save_settings(self, settings: dict[str, str | int]) -> None:
        lines = [
            f'api_port = {settings["api_port"]}',
            f'language = "{settings["language"]}"',
            f'telethon_api_id = "{settings.get("telethon_api_id", "")}"',
            f'telethon_api_hash = "{settings.get("telethon_api_hash", "")}"',
            f'telethon_phone = "{settings.get("telethon_phone", "")}"',
            f'telethon_session_path = "{settings.get("telethon_session_path", "")}"',
        ]
        self.settings_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

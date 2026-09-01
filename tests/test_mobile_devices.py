from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from telegram_parser.api import create_app
from telegram_parser.config import ChannelConfig, Settings
from telegram_parser.state import Resource, StateRepository


RESOURCE_ID = "6ed72443-ff82-42f5-b71b-caa3170d3807"
RULE_ID = "ballistics-kyiv"
RULE_KEY = f"{RESOURCE_ID}:{RULE_ID}"
TOKEN = "ExpoPushToken[device-token]"


def settings() -> Settings:
    return Settings(
        database_dsn="postgresql://test",
        normal_seconds=10,
        alert_seconds=2,
        alert_mode_minutes=180,
        api_host="127.0.0.1",
        api_port=8080,
        api_id=0,
        api_hash="",
        session_path="",
        notifier_endpoint="",
        notifier_secret="",
        escalation_patterns=(),
        critical_patterns=(),
        channels=(ChannelConfig("єРадар", "eRadarrua", "public"),),
    )


class FakeStore:
    def __init__(self, _dsn: str) -> None:
        self.devices: dict[str, tuple[int, list[tuple[str, str, str]]]] = {}

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def register_mobile_device(self, token: str, subscriptions: list[tuple[str, str, str]]) -> tuple[int, int]:
        device_id = self.devices.get(token, (len(self.devices) + 1, []))[0]
        self.devices[token] = (device_id, list(subscriptions))
        return device_id, len(subscriptions)


class MobileDevicesApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.state = StateRepository(Path(self.tempdir.name))
        self.state.save_resources([Resource(RESOURCE_ID, "https://t.me/eRadarrua", "eRadarrua", "public", "єРадар")])
        self.state.save_rules(
            {
                RESOURCE_ID: {
                    "items": [
                        {
                            "scenario": True,
                            "id": RULE_ID,
                            "title": "Балістика на Київ",
                            "operator": "and",
                            "items": [],
                        }
                    ]
                }
            }
        )
        self.store = FakeStore("postgresql://test")
        self.client = TestClient(create_app(settings(), self.state, store_factory=lambda _dsn: self.store))
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.tempdir.cleanup()

    def test_valid_token_registers_two_rules(self) -> None:
        second_key = f"{RESOURCE_ID}:shaheds-kyiv"
        self._add_rule("shaheds-kyiv", "Шахеди на Київ")

        response = self.client.post(
            "/api/mobile-devices",
            json={
                "expoPushToken": TOKEN,
                "preferences": {
                    RULE_KEY: {"enabled": True, "sound": "siren"},
                    second_key: {"enabled": True, "sound": "default"},
                },
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual({"registered": True, "device_id": 1, "subscriptions": 2}, response.json())
        self.assertEqual(2, len(self.store.devices[TOKEN][1]))

    def test_repeat_registration_replaces_subscriptions(self) -> None:
        self.client.post("/api/mobile-devices", json={"expoPushToken": TOKEN, "preferences": {RULE_KEY: {"enabled": True, "sound": "default"}}})

        response = self.client.post("/api/mobile-devices", json={"expoPushToken": TOKEN, "preferences": {RULE_KEY: {"enabled": True, "sound": "siren"}}})

        self.assertEqual(200, response.status_code)
        self.assertEqual([(RESOURCE_ID, RULE_ID, "siren")], self.store.devices[TOKEN][1])

    def test_disabled_preference_creates_no_subscription(self) -> None:
        response = self.client.post("/api/mobile-devices", json={"expoPushToken": TOKEN, "preferences": {RULE_KEY: {"enabled": False, "sound": "default"}}})

        self.assertEqual(200, response.status_code)
        self.assertEqual(0, response.json()["subscriptions"])

    def test_invalid_token_is_rejected(self) -> None:
        response = self.client.post("/api/mobile-devices", json={"expoPushToken": "not-an-expo-token", "preferences": {}})

        self.assertEqual(422, response.status_code)

    def test_unknown_rule_is_rejected(self) -> None:
        response = self.client.post("/api/mobile-devices", json={"expoPushToken": TOKEN, "preferences": {f"{RESOURCE_ID}:missing": {"enabled": True, "sound": "default"}}})

        self.assertEqual(422, response.status_code)

    def test_invalid_sound_is_rejected(self) -> None:
        response = self.client.post("/api/mobile-devices", json={"expoPushToken": TOKEN, "preferences": {RULE_KEY: {"enabled": True, "sound": "loud"}}})

        self.assertEqual(422, response.status_code)

    def _add_rule(self, rule_id: str, title: str) -> None:
        # State is intentionally reloadable by the endpoint, like production's mounted state directory.
        rules = self.state.load_rules()
        rules[RESOURCE_ID]["items"].append({"scenario": True, "id": rule_id, "title": title, "operator": "and", "items": []})
        self.state.save_rules(rules)

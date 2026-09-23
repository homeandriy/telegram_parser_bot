from __future__ import annotations

import unittest

from telegram_parser.alerts.client import active_air_raid_alerts, active_air_raid_location_uids


class ActiveAirRaidLocationUidsTest(unittest.TestCase):
    def test_returns_location_and_oblast_uids_for_active_air_raid(self) -> None:
        result = active_air_raid_location_uids(
            {
                "alerts": [
                    {
                        "alert_type": "air_raid",
                        "finished_at": None,
                        "location_uid": "124",
                        "location_oblast_uid": "21",
                    }
                ]
            }
        )

        self.assertEqual(frozenset({"124", "21"}), result)

    def test_ignores_finished_and_non_air_raid_alerts(self) -> None:
        result = active_air_raid_location_uids(
            {
                "alerts": [
                    {"alert_type": "chemical", "finished_at": None, "location_uid": "10"},
                    {"alert_type": "air_raid", "finished_at": "2026-09-01T00:00:00Z", "location_uid": "11"},
                ]
            }
        )

        self.assertEqual(frozenset(), result)

    def test_tolerates_malformed_payload(self) -> None:
        self.assertEqual(frozenset(), active_air_raid_location_uids({"alerts": "unexpected"}))

    def test_normalizes_all_active_air_raid_alerts_for_map_clients(self) -> None:
        alerts = active_air_raid_alerts(
            {
                "alerts": [
                    {
                        "id": 42,
                        "alert_type": "air_raid",
                        "finished_at": None,
                        "location_uid": 31,
                        "location_title": "м. Київ",
                        "location_type": "Місто з спеціальним статусом",
                        "location_oblast_uid": 31,
                        "location_oblast": "м. Київ",
                        "started_at": "2026-09-23T10:00:00Z",
                        "updated_at": "2026-09-23T10:01:00Z",
                    },
                    {"alert_type": "chemical", "finished_at": None, "location_uid": 10},
                    {"alert_type": "air_raid", "finished_at": "2026-09-23T10:00:00Z", "location_uid": 11},
                ]
            }
        )

        self.assertEqual(1, len(alerts))
        self.assertEqual("31", alerts[0].location_uid)
        self.assertEqual("м. Київ", alerts[0].location_title)

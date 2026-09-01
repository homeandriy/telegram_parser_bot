"""alerts.in.ua administrative-location reference data."""

from __future__ import annotations

import csv
import io
from importlib.resources import files
from dataclasses import dataclass

OBLAST_TYPE = "Область"
RAION_TYPE = "Район"
SPECIAL_CITY_TYPE = "Місто з спеціальним статусом"


@dataclass(frozen=True)
class AlertLocation:
    uid: int
    title: str
    location_type: str
    oblast_uid: int | None
    raion_uid: int | None


def parse_locations_csv(content: str) -> list[AlertLocation]:
    """Parse the published UID sheet and preserve its oblast/raion hierarchy."""
    lines = content.lstrip("\ufeff").splitlines()
    header_index = next((index for index, line in enumerate(lines) if line.startswith("UID,")), None)
    if header_index is None:
        raise ValueError("Location UID CSV header is missing")
    rows = csv.DictReader(io.StringIO("\n".join(lines[header_index:])))
    locations: list[AlertLocation] = []
    current_oblast_uid: int | None = None
    current_raion_uid: int | None = None
    for row in rows:
        raw_uid = (row.get("UID") or "").strip()
        title = (row.get("Назва") or "").strip()
        location_type = (row.get("Тип") or "").strip()
        if not raw_uid or not title or not location_type:
            continue
        uid = int(raw_uid)
        if location_type == OBLAST_TYPE:
            current_oblast_uid, current_raion_uid = uid, None
            oblast_uid, raion_uid = None, None
        elif location_type == SPECIAL_CITY_TYPE:
            current_oblast_uid, current_raion_uid = None, None
            oblast_uid, raion_uid = None, None
        elif location_type == RAION_TYPE:
            current_raion_uid = uid
            oblast_uid, raion_uid = current_oblast_uid, None
        else:
            oblast_uid, raion_uid = current_oblast_uid, current_raion_uid
        locations.append(AlertLocation(uid, title, location_type, oblast_uid, raion_uid))
    return locations


def load_bundled_locations() -> list[AlertLocation]:
    """Load the versioned Location UID snapshot shipped with every build."""
    content = files("telegram_parser.alerts").joinpath("data/location_uids.csv").read_text(encoding="utf-8")
    return parse_locations_csv(content)

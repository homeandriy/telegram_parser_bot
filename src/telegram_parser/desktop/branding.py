"""Resolve bundled brand assets in development and PyInstaller builds."""

from __future__ import annotations

import sys
from pathlib import Path


def asset_path(filename: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "assets" / filename  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[3] / "assets" / filename

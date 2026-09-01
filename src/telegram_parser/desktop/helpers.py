"""Small, offline-safe Qt icon helpers for visible UI actions."""

from __future__ import annotations

from PySide6.QtWidgets import QAbstractButton, QStyle


def set_button_icon(button: QAbstractButton, pixmap: QStyle.StandardPixmap, tooltip: str) -> None:
    button.setIcon(button.style().standardIcon(pixmap))
    button.setToolTip(tooltip)
    button.setAccessibleName(button.text())

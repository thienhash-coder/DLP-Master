from __future__ import annotations

try:
    from PyQt6.QtWidgets import QVBoxLayout, QWidget
except ImportError:
    from PySide6.QtWidgets import QVBoxLayout, QWidget

from .card import CardFrame


class SettingsCard(CardFrame):
    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(title, parent)

    def content_layout(self) -> QVBoxLayout:
        return self.body_layout()

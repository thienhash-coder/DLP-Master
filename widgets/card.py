from __future__ import annotations

try:
    from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget
except ImportError:
    from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class CardFrame(QFrame):
    """Reusable card container used across pages for consistent spacing and style."""

    def __init__(self, title: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(12)

        self.title_label: QLabel | None = None
        if title:
            self.title_label = QLabel(title)
            self.title_label.setObjectName("CardTitle")
            self.layout.addWidget(self.title_label)

    def body_layout(self) -> QVBoxLayout:
        return self.layout

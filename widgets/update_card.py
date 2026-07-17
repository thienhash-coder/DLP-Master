from __future__ import annotations

try:
    from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextBrowser, QWidget
except ImportError:
    from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextBrowser, QWidget

from .settings_card import SettingsCard


class UpdateCard(SettingsCard):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("Cập nhật", parent)
        layout = self.content_layout()

        self.current_label = QLabel("Phiên bản hiện tại: -")
        self.latest_label = QLabel("Phiên bản mới nhất: -")
        self.status_label = QLabel("Trạng thái: -")

        channel_row = QHBoxLayout()
        self.channel_caption = QLabel("Kênh cập nhật")
        self.channel_combo = QComboBox()
        self.channel_combo.addItems(["stable", "beta", "nightly"])
        channel_row.addWidget(self.channel_caption)
        channel_row.addWidget(self.channel_combo, 1)

        self.check_button = QPushButton("Kiểm tra cập nhật")
        self.install_button = QPushButton("Cài đặt")
        self.install_button.setEnabled(False)

        button_row = QHBoxLayout()
        button_row.addWidget(self.check_button)
        button_row.addWidget(self.install_button)
        button_row.addStretch(1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        self.progress_meta = QLabel("Đã tải: - | Tốc độ: - | Thời gian còn lại: -")
        self.progress_meta.setWordWrap(True)
        self.notes = QTextBrowser()
        self.notes.setMaximumHeight(120)
        self.notes.setPlainText("Có gì mới: -")

        for widget in (
            self.current_label,
            self.latest_label,
            self.status_label,
            self.progress,
            self.progress_meta,
            self.notes,
        ):
            layout.addWidget(widget)
        layout.addLayout(channel_row)
        layout.addLayout(button_row)

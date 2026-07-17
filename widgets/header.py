from __future__ import annotations

try:
    from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QWidget
except ImportError:
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QWidget


class StatusChip(QFrame):
    def __init__(self, title: str, value: str, state: str = "neutral", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("HeaderChip")
        self.setProperty("state", state)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("HeaderChipTitle")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("HeaderChipValue")
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, text: str, state: str | None = None):
        self.value_label.setText(text)
        if state is not None:
            self.setProperty("state", state)
            self.style().unpolish(self)
            self.style().polish(self)


class AppHeader(QFrame):
    def __init__(self, app_name: str, version: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("TopHeader")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        self.logo = QLabel("DLP")
        self.logo.setObjectName("HeaderLogo")
        self.app_title = QLabel(app_name)
        self.app_title.setObjectName("HeaderTitle")
        self.version_label = QLabel(f"v{version}")
        self.version_label.setObjectName("HeaderVersion")

        layout.addWidget(self.logo)
        layout.addWidget(self.app_title)
        layout.addWidget(self.version_label)
        layout.addStretch(1)

        self.connection_chip = StatusChip("Kết nối", "Sẵn sàng", "ok")
        self.engine_chip = StatusChip("Công cụ tải", "yt-dlp + FFmpeg", "ok")
        self.connection_chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.engine_chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.connection_chip.setToolTip("Trạng thái kết nối mạng và cập nhật ứng dụng.")
        self.engine_chip.setToolTip("Trạng thái công cụ tải và khả năng xử lý media.")

        layout.addWidget(self.connection_chip)
        layout.addWidget(self.engine_chip)

    def set_connection_status(self, text: str, state: str = "neutral"):
        self.connection_chip.set_value(text, state)

    def set_engine_status(self, text: str, state: str = "neutral"):
        self.engine_chip.set_value(text, state)

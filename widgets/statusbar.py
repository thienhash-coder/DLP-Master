from __future__ import annotations

try:
    from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget
except ImportError:
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget


class AppStatusBar(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("BottomStatusBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(16)

        self.downloads_label = QLabel(self._f("Đang tải", count=0))
        self.threads_label = QLabel(self._f("Luồng hoạt động", count=0))
        self.cookie_label = QLabel(self._f("Cookie", value="Ẩn danh"))
        self.network_label = QLabel(self._f("Mạng", value="Đang kiểm tra"))

        for label in (self.downloads_label, self.threads_label, self.cookie_label, self.network_label):
            label.setObjectName("BottomStatusItem")
            layout.addWidget(label)

        layout.addStretch(1)

    def set_metrics(self, queued_count: int, active_threads: int, cookie_ready: bool, network_text: str = "Unknown"):
        self.downloads_label.setText(self._f("Đang tải", count=queued_count))
        self.threads_label.setText(self._f("Luồng hoạt động", count=active_threads))
        cookie_value = "Đã đăng nhập" if cookie_ready else "Ẩn danh"
        self.cookie_label.setText(self._f("Cookie", value=cookie_value))

        normalized = str(network_text or "").strip().lower()
        if normalized == "online":
            network_value = "Đã kết nối"
        elif normalized == "offline":
            network_value = "Mất kết nối"
        else:
            network_value = "Đang kiểm tra"
        self.network_label.setText(self._f("Mạng", value=network_value))

    def _f(self, label: str, **kwargs) -> str:
        if "count" in kwargs:
            return f"{label}: {kwargs['count']}"
        if "value" in kwargs:
            return f"{label}: {kwargs['value']}"
        return label

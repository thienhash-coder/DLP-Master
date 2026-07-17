from __future__ import annotations

try:
    from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextBrowser, QVBoxLayout
except ImportError:
    from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextBrowser, QVBoxLayout


class UpdateDialog(QDialog):
    def __init__(self, current_version: str, latest_version: str, release_notes: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cập nhật DLP Master")
        self.resize(560, 360)
        self.setModal(True)

        layout = QVBoxLayout(self)
        self.title = QLabel(f"DLP Master v{latest_version} đã sẵn sàng")
        self.title.setObjectName("SectionTitle")
        self.version_label = QLabel(
            f"Phiên bản hiện tại: v{current_version} | Mới nhất: v{latest_version}"
        )
        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(True)
        self.notes.setPlainText(release_notes or "Không có ghi chú phiên bản.")

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status = QLabel("Sẵn sàng tải cập nhật.")
        self.status.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.skip_button = QPushButton("Bỏ qua phiên bản")
        self.later_button = QPushButton("Nhắc sau")
        self.download_button = QPushButton("Tải xuống")
        self.install_button = QPushButton("Cài đặt")
        self.cancel_button = QPushButton("Hủy")
        self.install_button.setEnabled(False)
        self.cancel_button.setEnabled(False)

        for button in (self.skip_button, self.later_button, self.download_button, self.install_button, self.cancel_button):
            buttons.addWidget(button)

        layout.addWidget(self.title)
        layout.addWidget(self.version_label)
        layout.addWidget(self.notes, 1)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        layout.addLayout(buttons)

    def set_progress(self, percent: int, status: str):
        self.progress.setValue(max(0, min(int(percent), 100)))
        self.status.setText(status)

    def set_download_running(self, running: bool):
        self.download_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.skip_button.setEnabled(not running)
        self.later_button.setEnabled(not running)

    def set_ready_to_install(self, ready: bool):
        self.install_button.setEnabled(ready)
        self.cancel_button.setEnabled(False)
        self.download_button.setEnabled(not ready)

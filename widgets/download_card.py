from __future__ import annotations

try:
    from PyQt6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLineEdit, QPushButton, QWidget
except ImportError:
    from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLineEdit, QPushButton, QWidget

from .card import CardFrame


class DownloadCard(CardFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("Tải xuống", parent)
        layout = self.body_layout()

        top_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Dán một hoặc nhiều liên kết, mỗi dòng một URL")
        self.start_button = QPushButton("Bắt đầu tải")
        self.start_button.setObjectName("StartButton")
        self.start_button.setToolTip("Bắt đầu tải các liên kết trong ô nhập.")
        top_row.addWidget(self.url_input, 1)
        top_row.addWidget(self.start_button)

        options_row = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "Mặc định",
            "Video",
            "Âm thanh",
            "Danh sách phát",
        ])
        self.quality_combo = QComboBox()
        self.quality_combo.addItems([
            "Tốt nhất",
            "1080p",
            "720p",
            "Chỉ âm thanh",
        ])
        self.output_input = QLineEdit()
        self.output_input.setPlaceholderText("Thư mục lưu")
        self.browse_button = QPushButton("Chọn thư mục")

        options_row.addWidget(self.preset_combo)
        options_row.addWidget(self.quality_combo)
        options_row.addWidget(self.output_input, 1)
        options_row.addWidget(self.browse_button)

        actions_row = QHBoxLayout()
        self.pause_button = QPushButton("Tạm dừng")
        self.resume_button = QPushButton("Tiếp tục")
        self.retry_button = QPushButton("Tải lại")
        self.delete_button = QPushButton("Xóa")
        self.pause_button.setToolTip("Tạm dừng tác vụ đang chọn trong hàng đợi.")
        self.resume_button.setToolTip("Tiếp tục tác vụ đang tạm dừng.")
        self.retry_button.setToolTip("Tạo tác vụ mới để tải lại liên kết đã chọn.")
        self.delete_button.setToolTip("Xóa tác vụ đã chọn khỏi hàng đợi.")
        for button in (self.pause_button, self.resume_button, self.retry_button, self.delete_button):
            actions_row.addWidget(button)
        actions_row.addStretch(1)

        self.queue_placeholder = QFrame()
        self.queue_placeholder.setObjectName("QueuePlaceholder")
        self.queue_placeholder.setMinimumHeight(220)

        layout.addLayout(top_row)
        layout.addLayout(options_row)
        layout.addLayout(actions_row)
        layout.addWidget(self.queue_placeholder, 1)

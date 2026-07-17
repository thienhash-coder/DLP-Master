from __future__ import annotations

try:
    import qtawesome as qta
except Exception:
    qta = None

try:
    from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, pyqtSignal
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget
except ImportError:
    from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal as pyqtSignal
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget


def _icon(name: str, color: str) -> QIcon:
    if qta is None:
        return QIcon()
    try:
        return qta.icon(name, color=color)
    except Exception:
        return QIcon()


class SidebarButton(QPushButton):
    def __init__(self, text: str, icon_name: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName("SidebarButton")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(_icon(icon_name, "#c8d1dc"))
        self.setIconSize(self.iconSize())

        self._hover_anim = QPropertyAnimation(self, b"minimumHeight", self)
        self._hover_anim.setDuration(170)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setMinimumHeight(40)

    def enterEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self.minimumHeight())
        self._hover_anim.setEndValue(44)
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self.minimumHeight())
        self._hover_anim.setEndValue(40)
        self._hover_anim.start()
        super().leaveEvent(event)


class AppSidebar(QFrame):
    page_requested = pyqtSignal(int)
    login_requested = pyqtSignal()

    def __init__(self, app_name: str, version: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(248)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 16, 14, 16)
        layout.setSpacing(8)

        title_wrap = QFrame()
        title_wrap.setObjectName("SidebarBrand")
        title_layout = QVBoxLayout(title_wrap)
        title_layout.setContentsMargins(10, 10, 10, 10)
        title_layout.setSpacing(2)

        title = QLabel(app_name)
        title.setObjectName("SidebarTitle")
        subtitle = QLabel(f"v{version}")
        subtitle.setObjectName("SidebarSubtitle")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        layout.addWidget(title_wrap)

        self.buttons: list[SidebarButton] = []
        items = [
            ("Tải xuống", "Mở trang tải xuống để thêm liên kết và quản lý hàng đợi.", "fa5s.download"),
            ("Cài đặt", "Mở trang cài đặt ứng dụng, cookie và cập nhật.", "fa5s.sliders-h"),
            ("Nhật ký", "Xem nhật ký hoạt động và lỗi trong quá trình tải.", "fa5s.file-alt"),
            ("Hướng dẫn", "Xem hướng dẫn sử dụng DLP Master.", "fa5s.life-ring"),
        ]
        for idx, (label_text, tooltip_text, icon_name) in enumerate(items):
            btn = SidebarButton(label_text, icon_name)
            btn.setToolTip(tooltip_text)
            btn.clicked.connect(lambda _checked, i=idx: self.page_requested.emit(i))
            layout.addWidget(btn)
            self.buttons.append(btn)

        layout.addSpacing(8)
        self.login_button = QPushButton("Đăng nhập tài khoản")
        self.login_button.setObjectName("SidebarActionButton")
        self.login_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_button.setIcon(_icon("fa5s.user-lock", "#8ec5ff"))
        self.login_button.setToolTip("Đăng nhập tài khoản để lấy cookie cho nội dung bị giới hạn.")
        self.login_button.clicked.connect(self.login_requested.emit)
        layout.addWidget(self.login_button)
        layout.addStretch(1)

    def set_current(self, index: int):
        for i, button in enumerate(self.buttons):
            button.setChecked(i == index)

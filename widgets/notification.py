from __future__ import annotations

try:
    from PyQt6.QtCore import QEvent, QObject, QPoint, QPropertyAnimation, QTimer
    from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget
except ImportError:
    from PySide6.QtCore import QEvent, QObject, QPoint, QPropertyAnimation, QTimer
    from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class Toast(QFrame):
    def __init__(self, message: str, level: str, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setProperty("level", level)
        self.setWindowOpacity(0.0)
        self.setFixedWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        self.message_label = QLabel(message)
        self.message_label.setObjectName("ToastMessage")
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        self.fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        self.fade_in.setDuration(200)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(1.0)

        self.fade_out = QPropertyAnimation(self, b"windowOpacity", self)
        self.fade_out.setDuration(200)
        self.fade_out.setStartValue(1.0)
        self.fade_out.setEndValue(0.0)

        self.slide_in = QPropertyAnimation(self, b"pos", self)
        self.slide_in.setDuration(200)


class NotificationManager(QObject):
    def __init__(self, parent_window: QWidget):
        super().__init__(parent_window)
        self.window = parent_window
        self.window.installEventFilter(self)
        self.toasts: list[Toast] = []

    def eventFilter(self, watched, event):
        if watched is self.window and event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            self._reposition()
        return super().eventFilter(watched, event)

    def show(self, message: str, level: str = "info", duration_ms: int = 2600):
        toast = Toast(message, level, self.window)
        self.toasts.append(toast)
        toast.show()
        targets = self._reposition()
        target = targets.get(toast)
        if target is not None:
            start = QPoint(target.x() + 28, target.y())
            toast.move(start)
            toast.slide_in.setStartValue(start)
            toast.slide_in.setEndValue(target)
            toast.slide_in.start()
        toast.fade_in.start()

        timer = QTimer(toast)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda t=toast: self._hide_toast(t))
        timer.start(duration_ms)

    def _hide_toast(self, toast: Toast):
        if toast not in self.toasts:
            return

        def _cleanup():
            if toast in self.toasts:
                self.toasts.remove(toast)
            toast.deleteLater()
            self._reposition()

        toast.fade_out.finished.connect(_cleanup)
        toast.fade_out.start()

    def _reposition(self):
        if not self.toasts:
            return {}

        spacing = 8
        margin = 14
        x = self.window.width() - margin
        y = self.window.height() - margin
        positions = {}

        for toast in reversed(self.toasts):
            toast.adjustSize()
            size = toast.sizeHint()
            pos = QPoint(x - size.width(), y - size.height())
            positions[toast] = pos
            if toast.windowOpacity() > 0:
                toast.move(pos)
            y -= size.height() + spacing

        return positions

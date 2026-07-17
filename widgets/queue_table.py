from __future__ import annotations

try:
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QMenu, QTableWidget, QTableWidgetItem, QWidget
except ImportError:
    from PySide6.QtCore import Qt, Signal as pyqtSignal
    from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QMenu, QTableWidget, QTableWidgetItem, QWidget


class QueueTable(QTableWidget):
    pause_requested = pyqtSignal(str)
    resume_requested = pyqtSignal(str)
    retry_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    HEADERS = ["Trạng thái", "Tên video", "Tiến trình", "Tốc độ", "Thời gian còn lại", "Dung lượng", "Định dạng"]

    def __init__(self, parent: QWidget | None = None):
        self.headers = self.HEADERS.copy()
        super().__init__(0, len(self.headers), parent)
        self.setObjectName("QueueTable")
        self.setHorizontalHeaderLabels(self.headers)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._open_menu)

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for idx in range(2, len(self.headers)):
            header.setSectionResizeMode(idx, QHeaderView.ResizeMode.ResizeToContents)

    def add_row(self, task_id: str, values: list[str]):
        row = self.rowCount()
        self.insertRow(row)
        for col, value in enumerate(values[: len(self.headers)]):
            item = QTableWidgetItem(value)
            item.setData(Qt.ItemDataRole.UserRole, task_id)
            self.setItem(row, col, item)

    def find_row(self, task_id: str) -> int:
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item is None:
                continue
            if str(item.data(Qt.ItemDataRole.UserRole) or "") == task_id:
                return row
        return -1

    def update_row(self, task_id: str, values: list[str]):
        row = self.find_row(task_id)
        if row < 0:
            return
        for col, value in enumerate(values[: len(self.headers)]):
            item = self.item(row, col)
            if item is None:
                item = QTableWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, task_id)
                self.setItem(row, col, item)
            item.setText(value)

    def remove_row_by_task_id(self, task_id: str):
        row = self.find_row(task_id)
        if row >= 0:
            self.removeRow(row)

    def selected_task_id(self) -> str:
        row = self.currentRow()
        if row < 0:
            return ""
        item = self.item(row, 0)
        if item is None:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or "")

    def _open_menu(self, position):
        row = self.rowAt(position.y())
        if row < 0:
            return
        item = self.item(row, 0)
        if item is None:
            return
        task_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not task_id:
            return

        menu = QMenu(self)
        pause_action = menu.addAction("Tạm dừng")
        resume_action = menu.addAction("Tiếp tục")
        retry_action = menu.addAction("Tải lại")
        delete_action = menu.addAction("Xóa")

        action = menu.exec(self.viewport().mapToGlobal(position))
        if action == pause_action:
            self.pause_requested.emit(task_id)
        elif action == resume_action:
            self.resume_requested.emit(task_id)
        elif action == retry_action:
            self.retry_requested.emit(task_id)
        elif action == delete_action:
            self.delete_requested.emit(task_id)

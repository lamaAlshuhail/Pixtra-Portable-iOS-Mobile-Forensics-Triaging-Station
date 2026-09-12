from __future__ import annotations

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QStackedWidget


class SizedStack(QStackedWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.currentChanged.connect(self._on_current_changed)

    def _on_current_changed(self, _index: int) -> None:
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        widget = self.currentWidget()
        if widget is None:
            return super().sizeHint()
        return widget.sizeHint()

    def minimumSizeHint(self) -> QSize:
        widget = self.currentWidget()
        if widget is None:
            return super().minimumSizeHint()
        return widget.minimumSizeHint()

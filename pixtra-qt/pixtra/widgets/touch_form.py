from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLineEdit


FOCUS_YMARGIN = 200
FOCUS_RESCROLL_DELAY_MS = 100


class FocusableLineEdit(QLineEdit):

    focused_in = pyqtSignal()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focused_in.emit()

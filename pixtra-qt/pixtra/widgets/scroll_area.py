from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QScrollArea, QScroller, QWidget

from .touch_form import FOCUS_RESCROLL_DELAY_MS, FOCUS_YMARGIN


class TouchScrollArea(QScrollArea):

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setObjectName("contentArea")
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        QTimer.singleShot(0, self._install_kinetic_scroll)

    def _install_kinetic_scroll(self) -> None:
        viewport = self.viewport()
        if viewport is None:
            return
        QScroller.grabGesture(
            viewport,
            QScroller.ScrollerGestureType.LeftMouseButtonGesture,
        )

    def scroll_to_focused(
        self,
        widget: QWidget,
        ymargin: int = FOCUS_YMARGIN,
    ) -> None:
        self.ensureWidgetVisible(widget, 0, ymargin)
        QTimer.singleShot(
            FOCUS_RESCROLL_DELAY_MS,
            lambda: self.ensureWidgetVisible(widget, 0, ymargin),
        )

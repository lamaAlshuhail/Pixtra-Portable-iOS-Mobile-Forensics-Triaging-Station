from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from ..theme import (
    BG_CARD,
    BORDER_SUBTLE,
    CARD_RADIUS_BL,
    CARD_RADIUS_BR,
    CARD_RADIUS_TL,
    CARD_RADIUS_TR,
    GREEN_700,
    SURFACE_ALT,
    TEXT_SECONDARY,
    TOUCH_HEIGHT,
    apply_card_shadow,
)


class ListRow(QFrame):

    clicked = pyqtSignal(object)

    def __init__(
        self,
        body_widgets: list[QWidget],
        *,
        leading_icon: Optional[str] = None,
        evidence_band: bool = False,
        badge_text: Optional[str] = None,
        badge_variant: str = "default",
        payload: Optional[object] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._payload = payload
        self.setObjectName("listRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(TOUCH_HEIGHT)
        self.setStyleSheet(
            f"QFrame#listRow {{"
            f"  background: {BG_CARD};"
            f"  border: 1px solid {BORDER_SUBTLE};"
            f"  border-top-left-radius: {CARD_RADIUS_TL}px;"
            f"  border-top-right-radius: {CARD_RADIUS_TR}px;"
            f"  border-bottom-right-radius: {CARD_RADIUS_BR}px;"
            f"  border-bottom-left-radius: {CARD_RADIUS_BL}px;"
            f"}}"
            f"QFrame#listRow:hover {{"
            f"  background: {SURFACE_ALT};"
            f"}}"
        )
        apply_card_shadow(self)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 12, 0)
        row.setSpacing(0)

        if evidence_band:
            band = QFrame()
            band.setFixedWidth(3)
            band.setStyleSheet(f"background: {GREEN_700}; border: none;")
            row.addWidget(band)
        elif leading_icon:
            spacer = QFrame()
            spacer.setFixedWidth(12)
            spacer.setStyleSheet("background: transparent; border: none;")
            row.addWidget(spacer)
            ic = QLabel()
            ic.setFixedSize(20, 20)
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ic.setPixmap(icons.pixmap(leading_icon, size=18, color=GREEN_700))
            ic.setStyleSheet("background: transparent; border: none;")
            row.addWidget(ic)
        else:
            spacer = QFrame()
            spacer.setFixedWidth(12)
            spacer.setStyleSheet("background: transparent; border: none;")
            row.addWidget(spacer)

        body_col = QVBoxLayout()
        body_col.setContentsMargins(12, 8, 12, 8)
        body_col.setSpacing(2)
        for w in body_widgets:
            body_col.addWidget(w)
        row.addLayout(body_col, 1)

        if badge_text:
            badge = QLabel(badge_text)
            badge.setObjectName("listRowBadge")
            badge.setProperty("variant", badge_variant)
            style = badge.style()
            if style is not None:
                style.unpolish(badge)
                style.polish(badge)
            row.addWidget(badge)

        chev = QLabel()
        chev.setFixedSize(12, 12)
        chev.setPixmap(icons.pixmap("chevron_right", size=12, color=TEXT_SECONDARY))
        chev.setStyleSheet("background: transparent; border: none;")
        row.addWidget(chev)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._payload)
        super().mousePressEvent(e)

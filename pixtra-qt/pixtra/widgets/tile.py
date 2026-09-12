from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from ..theme import GREEN_700, TEXT_DISABLED, TILE_MIN_PX, apply_card_shadow


class Tile(QPushButton):

    tile_clicked = pyqtSignal(str)

    def __init__(
        self,
        page_id: str,
        icon_name: str,
        label: str,
        count: Optional[object] = None,
        disabled: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._page_id = page_id
        self._disabled = disabled
        self.setObjectName("tileDisabled" if disabled else "tile")
        self.setMinimumSize(TILE_MIN_PX, TILE_MIN_PX)
        self.setCursor(
            Qt.CursorShape.ForbiddenCursor if disabled else Qt.CursorShape.PointingHandCursor
        )
        self.setEnabled(not disabled)

        col = QVBoxLayout(self)
        col.setContentsMargins(12, 12, 12, 12)
        col.setSpacing(6)
        col.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_color = TEXT_DISABLED if disabled else GREEN_700
        icon_lbl = QLabel()
        icon_lbl.setPixmap(icons.pixmap(icon_name, size=36, color=icon_color))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background: transparent;")
        col.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        text_lbl = QLabel(label)
        text_lbl.setObjectName("tileLabelDisabled" if disabled else "tileLabel")
        text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_lbl.setWordWrap(True)
        col.addWidget(text_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.addStretch(1)
        self.badge = QLabel()
        self.badge.setObjectName("tileBadgeMuted" if disabled else "tileBadge")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if disabled:
            self.badge.setText(" - ")
        elif count is not None:
            self.badge.setText(str(count))
        else:
            self.badge.setVisible(False)
        badge_row.addWidget(self.badge)
        badge_row.addStretch(1)
        col.addLayout(badge_row)

        if not disabled:
            apply_card_shadow(self)
            self.clicked.connect(self._emit)

    def _emit(self) -> None:
        self.tile_clicked.emit(self._page_id)

    def set_count(self, count: Optional[object]) -> None:
        if self._disabled:
            return
        if count is None:
            self.badge.setVisible(False)
        else:
            self.badge.setVisible(True)
            self.badge.setText(str(count))

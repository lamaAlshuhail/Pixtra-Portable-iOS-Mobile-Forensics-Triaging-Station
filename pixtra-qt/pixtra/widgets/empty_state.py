from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from ..theme import (
    GREEN_700,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TOUCH_HEIGHT,
    TYPE_LG,
    TYPE_SM,
)


class EmptyState(QWidget):

    action_clicked = pyqtSignal()

    def __init__(
        self,
        *,
        icon_name: str = "inbox",
        title: str,
        subtitle: Optional[str] = None,
        action_label: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        col = QVBoxLayout(self)
        col.setContentsMargins(24, 32, 24, 32)
        col.setSpacing(8)
        col.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ic = QLabel()
        ic.setFixedSize(40, 40)
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic.setPixmap(icons.pixmap(icon_name, size=40, color=TEXT_SECONDARY))
        ic.setStyleSheet("background: transparent; border: none;")
        col.addWidget(ic, 0, Qt.AlignmentFlag.AlignCenter)

        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            f"QLabel {{"
            f"  color: {TEXT_PRIMARY};"
            f"  font-size: {TYPE_LG}px;"
            f"  font-weight: 600;"
            f"  background: transparent; border: none;"
            f"}}"
        )
        col.addWidget(title_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub_lbl.setWordWrap(True)
            sub_lbl.setStyleSheet(
                f"QLabel {{"
                f"  color: {TEXT_SECONDARY};"
                f"  font-size: {TYPE_SM}px;"
                f"  background: transparent; border: none;"
                f"}}"
            )
            col.addWidget(sub_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        if action_label:
            self.action_btn = QPushButton(action_label)
            self.action_btn.setObjectName("pillCreate")
            self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.action_btn.setMinimumHeight(TOUCH_HEIGHT)
            self.action_btn.setMinimumWidth(160)
            self.action_btn.clicked.connect(self.action_clicked.emit)
            col.addSpacing(8)
            col.addWidget(self.action_btn, 0, Qt.AlignmentFlag.AlignCenter)

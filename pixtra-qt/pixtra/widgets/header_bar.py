import os
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from .. import icons
from ..services import session as session_svc
from ..theme import HEADER_HEIGHT, WORDMARK_COLOR


class HeaderBar(QWidget):

    home_clicked = pyqtSignal()
    back_clicked = pyqtSignal()
    sign_out_requested = pyqtSignal()
    cancel_requested = pyqtSignal()
    breadcrumb_navigate = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("headerTopStrip")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(HEADER_HEIGHT)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 16, 0)
        row.setSpacing(8)

        self.back_btn = QPushButton()
        self.back_btn.setObjectName("backChevron")
        self.back_btn.setIcon(icons.qicon("arrow_left", size=18, color=WORDMARK_COLOR))
        self.back_btn.setIconSize(icons.icon_size(18))
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.clicked.connect(self.back_clicked.emit)
        self.back_btn.setVisible(False)
        row.addWidget(self.back_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        self.wordmark = QLabel("Pixtra")
        self.wordmark.setObjectName("wordmark")
        self.wordmark.setCursor(Qt.CursorShape.PointingHandCursor)
        self.wordmark.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self.wordmark.setMinimumHeight(28)
        self.wordmark.mousePressEvent = self._wordmark_pressed
        row.addWidget(self.wordmark, 0, Qt.AlignmentFlag.AlignVCenter)

        row.addStretch(1)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("wizardCancelBtn")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setMinimumHeight(36)
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        self.cancel_btn.setVisible(False)
        row.addWidget(self.cancel_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        self.user_name_lbl = QLabel("")
        self.user_name_lbl.setStyleSheet(
            f"color: {WORDMARK_COLOR}; font-size: 12px; "
            f"background: transparent;"
        )
        row.addWidget(self.user_name_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        self.role_pill = QLabel("")
        self.role_pill.setObjectName("rolePill")
        self.role_pill.setVisible(False)
        row.addWidget(self.role_pill, 0, Qt.AlignmentFlag.AlignVCenter)

        self.sign_out_btn = QPushButton("Sign out")
        self.sign_out_btn.setObjectName("headerSignOut")
        self.sign_out_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sign_out_btn.setStyleSheet(
            "QPushButton#headerSignOut { background: transparent; "
            f"color: {WORDMARK_COLOR}; border: none; "
            "font-size: 12px; padding: 4px 8px; }"
            "QPushButton#headerSignOut:hover { text-decoration: underline; }"
        )
        self.sign_out_btn.clicked.connect(self.sign_out_requested.emit)
        self.sign_out_btn.setVisible(False)
        row.addWidget(self.sign_out_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        session_svc.signals().authenticated.connect(self.refresh_user)
        session_svc.signals().session_expired.connect(self.refresh_user)
        self.refresh_user()

        if os.environ.get("PIXTRA_DEBUG_HEADER"):
            QTimer.singleShot(500, self._dump_geometry)

    def _wordmark_pressed(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.home_clicked.emit()

    def _dump_geometry(self) -> None:
        print(f"[header] bar={self.size().width()}x{self.size().height()} "
              f"wordmark.geometry={self.wordmark.geometry()} "
              f"wordmark.font={self.wordmark.font().family()!r}@"
              f"{self.wordmark.font().pixelSize()}px")

    def set_back_visible(self, visible: bool) -> None:
        self.back_btn.setVisible(visible)

    def set_wizard_mode(self, enabled: bool) -> None:
        self.cancel_btn.setVisible(enabled)

    def refresh_user(self) -> None:
        examiner = session_svc.get_current_examiner()
        if not examiner:
            self.user_name_lbl.setText("(not signed in)")
            self.role_pill.setVisible(False)
            self.sign_out_btn.setVisible(False)
            return
        self.user_name_lbl.setText(
            examiner.get("full_name") or examiner.get("username") or ""
        )
        role = (examiner.get("role") or "").lower()
        self.role_pill.setText(role.title() if role else "")
        self.role_pill.setProperty("role", role)
        style = self.role_pill.style()
        if style is not None:
            style.unpolish(self.role_pill)
            style.polish(self.role_pill)
        self.role_pill.setVisible(bool(role))
        self.sign_out_btn.setVisible(True)

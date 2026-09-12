from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..theme import apply_card_shadow


class SignupPage(QWidget):
    navigate_requested = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)

        center_row = QHBoxLayout()
        center_row.addStretch(1)

        card = QFrame()
        card.setObjectName("greenCard")
        card.setMinimumWidth(360)
        card.setMaximumWidth(420)
        apply_card_shadow(card, strong=True)

        col = QVBoxLayout(card)
        col.setContentsMargins(28, 28, 28, 28)
        col.setSpacing(14)

        title = QLabel("Create account")
        title.setStyleSheet(
            "color: #FFFFFF; font-size: 22px; font-weight: 800; background: transparent;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(title)

        subtitle = QLabel("New examiner enrolment")
        subtitle.setStyleSheet(
            "color: rgba(255,255,255,0.72); font-size: 12px; background: transparent;"
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(subtitle)

        col.addSpacing(6)

        for label_text, attr, placeholder, password in (
            ("Full name", "input_name", "Jane Examiner", False),
            ("Username", "input_user", "jane.examiner", False),
            ("Password", "input_pass", "••••••••", True),
            ("Confirm password", "input_pass2", "••••••••", True),
        ):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(
                "color: rgba(255,255,255,0.85); font-size: 11px; "
                "font-weight: 600; background: transparent;"
            )
            col.addWidget(lbl)
            edit = QLineEdit()
            edit.setObjectName("inputRoundOnGreen")
            edit.setPlaceholderText(placeholder)
            if password:
                edit.setEchoMode(QLineEdit.EchoMode.Password)
            setattr(self, attr, edit)
            col.addWidget(edit)

        col.addSpacing(6)

        signup_btn = QPushButton("Create account")
        signup_btn.setObjectName("pillSecondary")
        signup_btn.setStyleSheet(
            "QPushButton#pillSecondary { background: #FFFFFF; color: #1B5E3B; "
            "border: 1px solid #FFFFFF; }"
            "QPushButton#pillSecondary:hover { background: #EDF5EF; }"
        )
        signup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        signup_btn.clicked.connect(lambda: self.navigate_requested.emit("login"))
        col.addWidget(signup_btn)

        back_row = QHBoxLayout()
        back_row.addStretch(1)
        back_lbl = QLabel("Already have an account?")
        back_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.72); font-size: 12px; background: transparent;"
        )
        back_row.addWidget(back_lbl)
        back_link = QPushButton("Sign in")
        back_link.setObjectName("btnGhost")
        back_link.setStyleSheet(
            "QPushButton#btnGhost { color: #FFFFFF; font-weight: 700; }"
            "QPushButton#btnGhost:hover { background: rgba(255,255,255,0.12); }"
        )
        back_link.setCursor(Qt.CursorShape.PointingHandCursor)
        back_link.clicked.connect(lambda: self.navigate_requested.emit("login"))
        back_row.addWidget(back_link)
        back_row.addStretch(1)
        col.addLayout(back_row)

        center_row.addWidget(card)
        center_row.addStretch(1)
        outer.addLayout(center_row)
        outer.addStretch(1)

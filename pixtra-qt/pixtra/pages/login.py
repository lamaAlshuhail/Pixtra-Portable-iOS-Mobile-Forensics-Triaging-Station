from __future__ import annotations

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

from .. import api
from ..services import session as session_svc
from ..theme import DANGER, GREEN_700, TOUCH_HEIGHT, apply_card_shadow
from ..widgets.scroll_area import TouchScrollArea
from ..widgets.sized_stack import SizedStack
from ..widgets.touch_form import FocusableLineEdit


_VIEW_SIGN_IN = 0
_VIEW_CHANGE_PW = 1


class LoginPage(QWidget):
    authenticated = pyqtSignal(dict)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pending_username: Optional[str] = None

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        self.scroll = TouchScrollArea()
        page_layout.addWidget(self.scroll)

        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addSpacing(16)

        center = QHBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(0)
        center.addStretch(1)

        self.card = QFrame()
        self.card.setObjectName("roundCard")
        self.card.setMinimumWidth(380)
        self.card.setMaximumWidth(440)
        apply_card_shadow(self.card, strong=True)
        cl = QVBoxLayout(self.card)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)

        self.title = QLabel("Sign in")
        self.title.setStyleSheet(
            f"color: {GREEN_700}; font-size: 22px; font-weight: 800; "
            f"background: transparent;"
        )
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.title)
        self.subtitle = QLabel("Welcome back to Pixtra")
        self.subtitle.setObjectName("mutedText")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.subtitle)
        cl.addSpacing(6)

        self.stack = SizedStack()
        self.stack.addWidget(self._build_sign_in_view())
        self.stack.addWidget(self._build_change_pw_view())
        cl.addWidget(self.stack)

        self.error_lbl = QLabel("")
        self.error_lbl.setStyleSheet(
            f"color: {DANGER}; background: transparent; font-size: 12px;"
        )
        self.error_lbl.setWordWrap(True)
        self.error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_lbl.setVisible(False)
        cl.addWidget(self.error_lbl)

        center.addWidget(self.card)
        center.addStretch(1)
        outer.addLayout(center)
        outer.addStretch(1)

        self.scroll.setWidget(content)

        session_svc.signals().must_change_password.connect(
            self._on_must_change_password
        )

    def _scroll_to_focused(self, field: QWidget) -> None:
        self.scroll.scroll_to_focused(field)

    def _build_sign_in_view(self) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(16)

        self.input_user = FocusableLineEdit()
        self.input_user.setObjectName("inputRound")
        self.input_user.setPlaceholderText("Username")
        self.input_user.setMinimumHeight(TOUCH_HEIGHT)
        self.input_user.returnPressed.connect(self._submit_sign_in)
        self.input_user.focused_in.connect(
            lambda: self._scroll_to_focused(self.input_user)
        )
        col.addLayout(self._form_row("Username", self.input_user))

        self.input_pass = FocusableLineEdit()
        self.input_pass.setObjectName("inputRound")
        self.input_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pass.setPlaceholderText("••••••••")
        self.input_pass.setMinimumHeight(TOUCH_HEIGHT)
        self.input_pass.returnPressed.connect(self._submit_sign_in)
        self.input_pass.focused_in.connect(
            lambda: self._scroll_to_focused(self.input_pass)
        )
        col.addLayout(self._form_row("Password", self.input_pass))

        self.sign_in_btn = QPushButton("Sign in")
        self.sign_in_btn.setObjectName("pillCreate")
        self.sign_in_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sign_in_btn.setMinimumHeight(TOUCH_HEIGHT)
        self.sign_in_btn.clicked.connect(self._submit_sign_in)
        col.addWidget(self.sign_in_btn)
        return page

    def _build_change_pw_view(self) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(16)

        self.input_old_pw = FocusableLineEdit()
        self.input_old_pw.setObjectName("inputRound")
        self.input_old_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_old_pw.setMinimumHeight(TOUCH_HEIGHT)
        self.input_old_pw.focused_in.connect(
            lambda: self._scroll_to_focused(self.input_old_pw)
        )
        col.addLayout(self._form_row("Current password", self.input_old_pw))

        self.input_new_pw = FocusableLineEdit()
        self.input_new_pw.setObjectName("inputRound")
        self.input_new_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_new_pw.setMinimumHeight(TOUCH_HEIGHT)
        self.input_new_pw.focused_in.connect(
            lambda: self._scroll_to_focused(self.input_new_pw)
        )
        col.addLayout(self._form_row(
            "New password (min 8 chars)", self.input_new_pw,
        ))

        self.input_confirm_pw = FocusableLineEdit()
        self.input_confirm_pw.setObjectName("inputRound")
        self.input_confirm_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_confirm_pw.setMinimumHeight(TOUCH_HEIGHT)
        self.input_confirm_pw.returnPressed.connect(self._submit_change_pw)
        self.input_confirm_pw.focused_in.connect(
            lambda: self._scroll_to_focused(self.input_confirm_pw)
        )
        col.addLayout(self._form_row(
            "Confirm new password", self.input_confirm_pw,
        ))

        self.change_pw_btn = QPushButton("Set new password")
        self.change_pw_btn.setObjectName("pillCreate")
        self.change_pw_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.change_pw_btn.setMinimumHeight(TOUCH_HEIGHT)
        self.change_pw_btn.clicked.connect(self._submit_change_pw)
        col.addWidget(self.change_pw_btn)
        return page

    @staticmethod
    def _label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("formLabel")
        return lbl

    def _form_row(self, label_text: str, field: QLineEdit) -> QVBoxLayout:
        row = QVBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addWidget(self._label(label_text))
        row.addWidget(field)
        return row

    def show_sign_in(self) -> None:
        self.title.setText("Sign in")
        self.subtitle.setText("Welcome back to Pixtra")
        self.error_lbl.setVisible(False)
        self.input_pass.clear()
        self.stack.setCurrentIndex(_VIEW_SIGN_IN)
        self._set_busy(False)

    def show_change_password(self, *, reset_by_supervisor: bool = False) -> None:
        if reset_by_supervisor:
            self.title.setText("Set a new password")
            self.subtitle.setText(
                "Your supervisor reset your password - set a new one now."
            )
        else:
            self.title.setText("Change your password")
            self.subtitle.setText(
                "Pixtra requires a password change at first login."
            )
        self.error_lbl.setVisible(False)
        self.input_old_pw.clear()
        self.input_new_pw.clear()
        self.input_confirm_pw.clear()
        self.stack.setCurrentIndex(_VIEW_CHANGE_PW)
        self._set_busy(False)

    def _submit_sign_in(self) -> None:
        username = self.input_user.text().strip()
        password = self.input_pass.text()
        if not username or not password:
            self._show_error("Username and password are required")
            return
        self.error_lbl.setVisible(False)
        self._set_busy(True)
        self._pending_username = username
        api.run_async(
            api.post,
            on_result=self._on_sign_in_result,
            on_error=self._on_sign_in_error,
            path="/auth/login",
            body={"username": username, "password": password},
        )

    def _on_sign_in_result(self, data) -> None:
        self._set_busy(False)
        if not isinstance(data, dict) or "token" not in data:
            self._show_error("Unexpected login response")
            return
        examiner = data.get("examiner") or {}
        session_svc.set_token(data["token"])
        session_svc.set_current_examiner(examiner)
        self.error_lbl.setVisible(False)
        if examiner.get("must_change_password"):
            self.show_change_password()
        else:
            self.authenticated.emit(examiner)

    def _on_sign_in_error(self, msg: str) -> None:
        self._set_busy(False)
        text = str(msg)
        if "401" in text:
            self._show_error("Invalid credentials")
        elif "429" in text:
            self._show_error("Account locked. Try again in a few minutes.")
        else:
            self._show_error(text or "Sign in failed")

    def _submit_change_pw(self) -> None:
        old = self.input_old_pw.text()
        new = self.input_new_pw.text()
        confirm = self.input_confirm_pw.text()
        if not old or not new:
            self._show_error("All fields are required")
            return
        if len(new) < 8:
            self._show_error("New password must be at least 8 characters")
            return
        if new != confirm:
            self._show_error("New passwords do not match")
            return
        if new == old:
            self._show_error("New password must differ from the current one")
            return
        self._set_busy(True)
        api.run_async(
            api.post,
            on_result=self._on_change_pw_result,
            on_error=self._on_change_pw_error,
            path="/auth/change-password",
            body={"old_password": old, "new_password": new},
        )

    def _on_change_pw_result(self, _data) -> None:
        self._set_busy(False)
        api.run_async(
            api.get,
            on_result=self._after_change_pw_me,
            on_error=lambda _e: self._after_change_pw_me(None),
            path="/auth/me",
        )

    def _after_change_pw_me(self, data) -> None:
        examiner = (
            (data or {}).get("examiner") if isinstance(data, dict) else None
        ) or session_svc.get_current_examiner() or {}
        examiner["must_change_password"] = False
        session_svc.set_current_examiner(examiner)
        self.authenticated.emit(examiner)

    def _on_change_pw_error(self, msg: str) -> None:
        self._set_busy(False)
        text = str(msg)
        if "401" in text:
            self._show_error("Current password incorrect")
        elif "400" in text:
            self._show_error(
                "Password rejected - must be 8+ chars and differ from current"
            )
        else:
            self._show_error(text or "Password change failed")

    def _on_must_change_password(self) -> None:
        self.show_change_password(reset_by_supervisor=True)

    def _show_error(self, text: str) -> None:
        self.error_lbl.setText(text)
        self.error_lbl.setVisible(True)

    def _set_busy(self, busy: bool) -> None:
        for btn in (self.sign_in_btn, self.change_pw_btn):
            btn.setEnabled(not busy)
        self.sign_in_btn.setText("Signing in…" if busy else "Sign in")
        self.change_pw_btn.setText(
            "Saving…" if busy else "Set new password"
        )

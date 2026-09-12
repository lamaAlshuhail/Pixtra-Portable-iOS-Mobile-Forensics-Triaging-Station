from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import api, icons
from ..format import fmt, fmt_time
from ..services import session as session_svc
from ..state import AppState
from ..theme import GREEN_700, apply_card_shadow
from ..touch import enable_touch_scroll


_ROLE_LABELS = {
    "supervisor": "Supervisor",
    "examiner": "Examiner",
    "viewer": "Viewer",
}


class _UserDialog(QDialog):

    def __init__(
        self,
        mode: str,
        user: Optional[dict] = None,
        is_self: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.mode = mode
        self.user = user or {}
        self.is_self = is_self
        self.setWindowTitle({
            "create": "Add examiner",
            "edit": "Edit examiner",
            "reset": "Reset password",
        }[mode])
        self.setMinimumWidth(360)

        col = QVBoxLayout(self)
        col.setContentsMargins(16, 16, 16, 16)
        col.setSpacing(10)

        if mode in ("create", "edit"):
            col.addWidget(self._lbl("Username"))
            self.input_username = QLineEdit(self.user.get("username", ""))
            if mode == "edit":
                self.input_username.setReadOnly(True)
                self.input_username.setStyleSheet("color: #888888;")
            col.addWidget(self.input_username)

            col.addWidget(self._lbl("Full name"))
            self.input_fullname = QLineEdit(self.user.get("full_name", ""))
            col.addWidget(self.input_fullname)

            col.addWidget(self._lbl("Email (optional)"))
            self.input_email = QLineEdit(self.user.get("email") or "")
            col.addWidget(self.input_email)

            col.addWidget(self._lbl("Role"))
            self.combo_role = QComboBox()
            for k, v in _ROLE_LABELS.items():
                self.combo_role.addItem(v, k)
            current = self.user.get("role", "examiner")
            for i in range(self.combo_role.count()):
                if self.combo_role.itemData(i) == current:
                    self.combo_role.setCurrentIndex(i)
                    break
            if mode == "edit" and is_self:
                self.combo_role.setEnabled(False)
                self.combo_role.setToolTip("Cannot modify own role")
            col.addWidget(self.combo_role)

        if mode == "create":
            col.addWidget(self._lbl("Initial password (min 8 chars)"))
            self.input_password = QLineEdit()
            self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
            col.addWidget(self.input_password)

        if mode == "reset":
            col.addWidget(self._lbl(
                f"Reset password for {self.user.get('username', '?')}"
            ))
            self.input_password = QLineEdit()
            self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
            self.input_password.setPlaceholderText("New password (min 8 chars)")
            col.addWidget(self.input_password)
            note = QLabel(
                "The user will be forced to change this password on "
                "their next sign-in."
            )
            note.setObjectName("subtle")
            note.setWordWrap(True)
            col.addWidget(note)

        if mode == "edit":
            col.addWidget(self._lbl("Status"))
            self.btn_active = QPushButton(
                "Active" if self.user.get("is_active") else "Deactivated"
            )
            self.btn_active.setCheckable(True)
            self.btn_active.setChecked(bool(self.user.get("is_active")))
            self.btn_active.toggled.connect(
                lambda checked: self.btn_active.setText(
                    "Active" if checked else "Deactivated"
                )
            )
            if is_self:
                self.btn_active.setEnabled(False)
                self.btn_active.setToolTip("Cannot deactivate self")
            col.addWidget(self.btn_active)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        col.addWidget(bb)

    @staticmethod
    def _lbl(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("formLabel")
        return lbl

    def payload(self) -> dict:
        out: dict = {}
        if self.mode == "create":
            out = {
                "username": self.input_username.text().strip(),
                "full_name": self.input_fullname.text().strip(),
                "email": self.input_email.text().strip() or None,
                "role": self.combo_role.currentData(),
                "password": self.input_password.text(),
            }
        elif self.mode == "edit":
            out = {
                "full_name": self.input_fullname.text().strip(),
                "email": self.input_email.text().strip() or None,
                "is_active": self.btn_active.isChecked(),
            }
            if not self.is_self:
                out["role"] = self.combo_role.currentData()
        elif self.mode == "reset":
            out = {"new_password": self.input_password.text()}
        return out


class UsersPage(QWidget):
    navigate_requested = pyqtSignal(str)
    toast = pyqtSignal(str)

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._users: list[dict] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setObjectName("contentArea")
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        enable_touch_scroll(self.scroll)
        host = QWidget()
        col = QVBoxLayout(host)
        col.setContentsMargins(8, 8, 8, 8)
        col.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(8)
        title = QLabel("Manage Examiners")
        title.setStyleSheet(
            "font-size: 22px; font-weight: 800; background: transparent;"
        )
        top.addWidget(title)
        self.count_label = QLabel("")
        self.count_label.setObjectName("mutedText")
        self.count_label.setStyleSheet(
            "background: transparent; padding-left: 8px;"
        )
        top.addWidget(self.count_label)
        top.addStretch(1)
        add_btn = QPushButton("Add examiner")
        add_btn.setObjectName("pillCreate")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_add)
        top.addWidget(add_btn)
        col.addLayout(top)

        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(6)
        col.addLayout(self.list_layout)
        col.addStretch(1)

        self.scroll.setWidget(host)
        outer.addWidget(self.scroll)


    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        api.run_async(
            api.get,
            on_result=self._on_loaded,
            on_error=lambda msg: self._render_status(f"Failed to load: {msg}"),
            path="/auth/users",
        )

    def _on_loaded(self, data) -> None:
        self._users = list((data or {}).get("users") or [])
        self.count_label.setText(
            f"{fmt(len(self._users))} account"
            + ("" if len(self._users) == 1 else "s")
        )
        self._render_list()

    def _clear_list(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _render_status(self, message: str) -> None:
        self._clear_list()
        lbl = QLabel(message)
        lbl.setObjectName("mutedText")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("background: transparent; padding: 32px 0;")
        self.list_layout.addWidget(lbl)

    def _render_list(self) -> None:
        self._clear_list()
        if not self._users:
            self._render_status("No accounts yet")
            return
        me = session_svc.get_current_examiner() or {}
        for u in self._users:
            self.list_layout.addWidget(
                self._build_row(u, is_self=u.get("id") == me.get("id"))
            )

    def _build_row(self, u: dict, is_self: bool) -> QFrame:
        frame = QFrame()
        frame.setObjectName("caseCard")
        apply_card_shadow(frame)
        row = QHBoxLayout(frame)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(12)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_lbl = QLabel(u.get("full_name") or "(no name)")
        name_lbl.setStyleSheet(
            "font-size: 14px; font-weight: 600; background: transparent;"
        )
        name_row.addWidget(name_lbl)
        if is_self:
            self_lbl = QLabel("you")
            self_lbl.setStyleSheet(
                f"QLabel {{ background: {GREEN_700}; color: #FFFFFF; "
                f"font-size: 10px; font-weight: 700; padding: 1px 6px; "
                f"border-radius: 8px; }}"
            )
            name_row.addWidget(self_lbl)
        if not u.get("is_active"):
            inactive_lbl = QLabel("Deactivated")
            inactive_lbl.setStyleSheet(
                "QLabel { background: #FDECEA; color: #C62828; "
                "font-size: 10px; font-weight: 700; padding: 1px 6px; "
                "border-radius: 8px; }"
            )
            name_row.addWidget(inactive_lbl)
        name_row.addStretch(1)
        nrw = QWidget()
        nrw.setLayout(name_row)
        text_col.addWidget(nrw)

        sub = QLabel(
            f"{u.get('username', '?')} · {_ROLE_LABELS.get(u.get('role', ''), u.get('role', '?'))}"
        )
        sub.setStyleSheet(
            "font-size: 12px; color: #888888; background: transparent;"
        )
        text_col.addWidget(sub)

        last = u.get("last_login_at")
        if last:
            last_lbl = QLabel(f"last login {fmt_time(last) or last}")
            last_lbl.setObjectName("subtle")
            text_col.addWidget(last_lbl)

        row.addLayout(text_col, 1)

        edit_btn = QPushButton("Edit")
        edit_btn.setObjectName("btnSm")
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.clicked.connect(lambda: self._on_edit(u, is_self))
        row.addWidget(edit_btn)

        reset_btn = QPushButton("Reset password")
        reset_btn.setObjectName("btnSm")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.clicked.connect(lambda: self._on_reset(u))
        row.addWidget(reset_btn)
        return frame

    def _on_add(self) -> None:
        dlg = _UserDialog(mode="create", parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dlg.payload()
        if len(payload.get("password") or "") < 8:
            self.toast.emit("Password must be at least 8 characters")
            return
        api.run_async(
            api.post,
            on_result=lambda _r: (self.toast.emit("Examiner created"), self.refresh()),
            on_error=lambda msg: self.toast.emit(f"Create failed: {msg}"),
            path="/auth/users",
            body=payload,
        )

    def _on_edit(self, u: dict, is_self: bool) -> None:
        dlg = _UserDialog(mode="edit", user=u, is_self=is_self, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dlg.payload()
        api.run_async(
            api.put,
            on_result=lambda _r: (self.toast.emit("Examiner updated"), self.refresh()),
            on_error=lambda msg: self.toast.emit(f"Update failed: {msg}"),
            path=f"/auth/users/{u['id']}",
            body=payload,
        )

    def _on_reset(self, u: dict) -> None:
        dlg = _UserDialog(mode="reset", user=u, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dlg.payload()
        if len(payload.get("new_password") or "") < 8:
            self.toast.emit("Password must be at least 8 characters")
            return
        api.run_async(
            api.post,
            on_result=lambda _r: self.toast.emit(
                f"Password reset for {u.get('username')}"
            ),
            on_error=lambda msg: self.toast.emit(f"Reset failed: {msg}"),
            path=f"/auth/users/{u['id']}/reset-password",
            body=payload,
        )

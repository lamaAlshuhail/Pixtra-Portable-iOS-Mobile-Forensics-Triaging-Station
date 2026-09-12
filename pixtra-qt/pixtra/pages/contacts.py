from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import api, icons
from ..format import initials
from ..state import AppState
from ..touch import enable_touch_scroll


class ContactsPage(QWidget):
    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._do_load)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        search = QFrame()
        search.setStyleSheet(
            "background: #FFFFFF; border: 1px solid #C8C8C0;"
        )
        search.setFixedHeight(42)
        sl = QHBoxLayout(search)
        sl.setContentsMargins(12, 0, 12, 0)
        sl.setSpacing(8)
        icon = QLabel()
        icon.setPixmap(icons.pixmap("search", size=16, color="#7A7A72"))
        sl.addWidget(icon)
        self.search_input = QLineEdit()
        self.search_input.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.search_input.setStyleSheet("border: none; background: transparent; font-size: 14px;")
        self.search_input.textChanged.connect(lambda _: self._debounce.start())
        sl.addWidget(self.search_input, 1)
        root.addWidget(search)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setObjectName("contentArea")
        enable_touch_scroll(self.scroll)
        self.container = QWidget()
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, 1)

        state.case_changed.connect(lambda _: self._do_load())

    def on_show(self) -> None:
        self._do_load()

    def _do_load(self) -> None:
        if not self.state.case_id:
            return
        q = self.search_input.text().strip()
        path = f"/analysis/evidence/{self.state.case_id}/contacts"
        params = {"search": q} if q and len(q) > 2 else None
        api.run_async(
            api.get,
            on_result=self._on_loaded,
            on_error=lambda msg: None,
            path=path,
            params=params,
        )

    def _on_loaded(self, data) -> None:
        self._clear()
        contacts = api.coerce_list(data, "contacts", "items")
        if not contacts:
            wrap = QWidget()
            wl = QVBoxLayout(wrap)
            wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ic = QLabel()
            ic.setPixmap(icons.pixmap("users", size=40, color="#98988F", stroke=1.5))
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            wl.addWidget(ic)
            msg = QLabel("No contacts")
            msg.setObjectName("mutedText")
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            wl.addWidget(msg)
            self.list_layout.addWidget(wrap)
            self.list_layout.addStretch()
            return

        for c in contacts:
            self.list_layout.addWidget(self._row(c))
        self.list_layout.addStretch()

    def _row(self, c: dict) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background: #FFFFFF; border-bottom: 1px solid #E8E8E2; }"
        )
        row = QHBoxLayout(frame)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)

        av = QLabel(initials(c.get("name")))
        av.setFixedSize(34, 34)
        av.setAlignment(Qt.AlignmentFlag.AlignCenter)
        av.setStyleSheet(
            "background: #D4EDDF; color: #14432A;"
            " font-weight: 700; font-size: 13px;"
        )
        row.addWidget(av)

        mid = QVBoxLayout()
        mid.setSpacing(0)
        name = QLabel(c.get("name") or "Unknown")
        name.setStyleSheet("font-size: 13px; font-weight: 600; background: transparent;")
        name.setWordWrap(True)
        mid.addWidget(name)

        phone_email = []
        if c.get("phone"):
            phone_email.append(c["phone"])
        if c.get("email"):
            phone_email.append(c["email"])
        sub = QLabel(" · ".join(phone_email))
        sub.setObjectName("subtle")
        sub.setWordWrap(True)
        mid.addWidget(sub)
        row.addLayout(mid, 1)

        if c.get("organization"):
            org = QLabel(c["organization"])
            org.setObjectName("subtle")
            row.addWidget(org)
        return frame

    def _clear(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

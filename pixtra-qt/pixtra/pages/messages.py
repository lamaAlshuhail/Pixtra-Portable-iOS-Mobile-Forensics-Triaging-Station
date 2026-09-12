from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class _ClickableFrame(QFrame):

    clicked = pyqtSignal(str, str)

    def __init__(self, chat_id: str, chat_name: str, parent=None) -> None:
        super().__init__(parent)
        self._chat_id = chat_id
        self._chat_name = chat_name
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._chat_id, self._chat_name)
        super().mousePressEvent(e)


from .. import api, icons
from ..format import fmt_time, initials
from ..state import AppState
from ..touch import enable_touch_scroll


_SOURCE_TITLES = {
    None: "Messages",
    "whatsapp": "WhatsApp",
    "imessage": "iMessage",
    "sms": "SMS",
    "instagram": "Instagram",
}

_FILTER_CHIPS = ("All", "Sent", "Received", "Documents", "Links", "Media")


class _SearchBox(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "background: #FFFFFF; border: 1px solid #C8C8C0;"
        )
        self.setFixedHeight(42)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        icon = QLabel()
        icon.setPixmap(icons.pixmap("search", size=16, color="#7A7A72"))
        layout.addWidget(icon)

        self.input = QLineEdit()
        self.input.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.input.setStyleSheet("border: none; background: transparent; font-size: 14px;")
        layout.addWidget(self.input, 1)


class MessagesPage(QWidget):
    def __init__(
        self,
        state: AppState,
        source: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.state = state
        self._source = source
        self._chats: list[dict] = []
        self._chats_total = 0
        self._chats_offset = 0
        self._chats_page_size = 50
        self._chats_loading_more = False
        self._messages_cache: list[dict] = []
        self._active_filter = "All"

        self.stack = QStackedWidget(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.stack)

        self.list_view = QWidget()
        lv = QVBoxLayout(self.list_view)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(8)

        title_row = QHBoxLayout()
        page_title = QLabel(_SOURCE_TITLES.get(self._source, "Messages"))
        page_title.setStyleSheet(
            "font-size: 22px; font-weight: 800; background: transparent;"
        )
        title_row.addWidget(page_title)
        title_row.addStretch(1)
        lv.addLayout(title_row)

        self.search_box = _SearchBox()
        self.search_box.input.returnPressed.connect(self._do_search)
        lv.addWidget(self.search_box)

        self.list_scroll = QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setObjectName("contentArea")
        enable_touch_scroll(self.list_scroll)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch()
        self.list_scroll.setWidget(self.list_container)
        lv.addWidget(self.list_scroll, 1)

        self.list_scroll.verticalScrollBar().valueChanged.connect(
            self._on_chats_scrolled
        )

        self.stack.addWidget(self.list_view)

        self.thread_view = QWidget()
        tv = QVBoxLayout(self.thread_view)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(6)

        back_btn = QPushButton("  Back")
        back_btn.setObjectName("btnGhost")
        back_btn.setIcon(icons.qicon("chevron_left", size=14, color="#62625F"))
        back_btn.setIconSize(icons.icon_size(14))
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        tv.addWidget(back_btn, 0, Qt.AlignmentFlag.AlignLeft)

        self.thread_title = QLabel("")
        self.thread_title.setStyleSheet("font-size: 13px; font-weight: 600; background: transparent;")
        tv.addWidget(self.thread_title)

        chips_row = QHBoxLayout()
        chips_row.setContentsMargins(0, 4, 0, 4)
        chips_row.setSpacing(6)
        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)
        for name in _FILTER_CHIPS:
            btn = QPushButton(name)
            btn.setObjectName("chipFilter")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if name == "All":
                btn.setChecked(True)
            btn.clicked.connect(lambda _checked, n=name: self._set_filter(n))
            self._chip_group.addButton(btn)
            chips_row.addWidget(btn)
        chips_row.addStretch(1)
        tv.addLayout(chips_row)

        self.thread_scroll = QScrollArea()
        self.thread_scroll.setWidgetResizable(True)
        self.thread_scroll.setObjectName("contentArea")
        enable_touch_scroll(self.thread_scroll)
        self.thread_container = QWidget()
        self.thread_layout = QVBoxLayout(self.thread_container)
        self.thread_layout.setContentsMargins(0, 0, 0, 0)
        self.thread_layout.setSpacing(4)
        self.thread_layout.addStretch()
        self.thread_scroll.setWidget(self.thread_container)
        tv.addWidget(self.thread_scroll, 1)

        self.stack.addWidget(self.thread_view)

        state.case_changed.connect(lambda _: self.refresh())

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        if not self.state.case_id:
            return
        self._chats = []
        self._chats_offset = 0
        self._chats_total = 0
        self._chats_loading_more = False
        self._clear_layout(self.list_layout)
        loading = QLabel("Loading chats...")
        loading.setObjectName("mutedText")
        loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.list_layout.addWidget(loading)
        self.list_layout.addStretch()
        self._fetch_chats_page()

    def _fetch_chats_page(self) -> None:
        params: dict = {"limit": self._chats_page_size, "offset": self._chats_offset}
        if self._source:
            params["source"] = self._source
        api.run_async(
            api.get,
            on_result=self._on_chats,
            on_error=lambda _msg: None,
            path=f"/analysis/evidence/{self.state.case_id}/chats",
            params=params,
        )

    def _on_chats(self, data) -> None:
        if isinstance(data, dict):
            self._chats_total = int(data.get("total") or 0)
        page = api.coerce_list(data, "chats", "items", "conversations")
        if self._source:
            page = [c for c in page if (c.get("source") or "").lower() == self._source]

        if self._chats_offset == 0:
            self._clear_layout(self.list_layout)
            self._chats = []

        self._chats.extend(page)

        if self.list_layout.count() and self.list_layout.itemAt(
            self.list_layout.count() - 1
        ).spacerItem() is not None:
            self.list_layout.takeAt(self.list_layout.count() - 1)

        if not self._chats:
            self._append_empty("message_square", "No conversations", self.list_layout)
            return

        for c in page:
            self.list_layout.addWidget(self._chat_row(c))
        self.list_layout.addStretch()

    def _load_more_chats(self) -> None:
        self._chats_offset += self._chats_page_size
        api.run_async(
            api.get,
            on_result=self._on_more_chats,
            on_error=lambda _msg: self._on_more_chats(None),
            path=f"/analysis/evidence/{self.state.case_id}/chats",
            params={
                "limit": self._chats_page_size,
                "offset": self._chats_offset,
                **({"source": self._source} if self._source else {}),
            },
        )

    def _on_more_chats(self, data) -> None:
        self._chats_loading_more = False
        self._on_chats(data)

    def _on_chats_scrolled(self, value: int) -> None:
        if self._chats_loading_more:
            return
        sb = self.list_scroll.verticalScrollBar()
        max_val = sb.maximum()
        if max_val <= 0:
            return
        if value < max_val - 200:
            return
        if not self._chats_total or len(self._chats) >= self._chats_total:
            return
        self._chats_loading_more = True
        self._load_more_chats()

    def _chat_row(self, c: dict) -> QFrame:
        chat_id = c.get("chat_id") or ""
        chat_name = c.get("chat_name") or chat_id or "Unknown"

        frame = _ClickableFrame(chat_id, chat_name)
        frame.setStyleSheet(
            "QFrame { background: #FFFFFF; border-bottom: 1px solid #E8E8E2; }"
        )
        frame.clicked.connect(self._open_chat)
        row = QHBoxLayout(frame)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)

        av = QLabel(initials(chat_name))
        av.setFixedSize(34, 34)
        av.setAlignment(Qt.AlignmentFlag.AlignCenter)
        av.setStyleSheet(
            "background: #D4EDDF; color: #14432A;"
            " font-weight: 700; font-size: 13px;"
        )
        row.addWidget(av)

        mid = QVBoxLayout()
        mid.setSpacing(0)
        name = QLabel(chat_name)
        name.setStyleSheet("font-size: 13px; font-weight: 600; background: transparent;")
        name.setWordWrap(True)
        mid.addWidget(name)
        sub = QLabel(f"{c.get('message_count', 0)} messages · {c.get('source', '')}")
        sub.setObjectName("subtle")
        sub.setWordWrap(True)
        mid.addWidget(sub)
        row.addLayout(mid, 1)

        right = QVBoxLayout()
        right.setAlignment(Qt.AlignmentFlag.AlignRight)
        last = QLabel(fmt_time(c.get("last_message")))
        last.setObjectName("subtle")
        last.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addWidget(last)
        cnt = QLabel(str(c.get("message_count", 0)))
        cnt.setObjectName("badgeGreen")
        cnt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(cnt)
        row.addLayout(right)
        return frame

    def _open_chat(self, chat_id: str, chat_name: str) -> None:
        self.thread_title.setText(chat_name)
        self._messages_cache = []
        self._active_filter = "All"
        for btn in self._chip_group.buttons():
            btn.setChecked(btn.text() == "All")
        self._clear_layout(self.thread_layout)
        loading = QLabel("Loading messages...")
        loading.setObjectName("mutedText")
        loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thread_layout.addWidget(loading)
        self.thread_layout.addStretch()
        self.stack.setCurrentIndex(1)
        params = {"chat_id": chat_id, "limit": 200}
        if self._source:
            params["source"] = self._source
        api.run_async(
            api.get,
            on_result=self._on_messages,
            on_error=lambda msg: None,
            path=f"/analysis/evidence/{self.state.case_id}/messages",
            params=params,
        )

    def _on_messages(self, data) -> None:
        messages = api.coerce_list(data, "messages", "items")
        if self._source:
            messages = [
                m for m in messages
                if (m.get("source") or "").lower() == self._source
            ]
        self._messages_cache = messages
        self._render_messages()

    def _set_filter(self, name: str) -> None:
        self._active_filter = name
        self._render_messages()

    def _render_messages(self) -> None:
        self._clear_layout(self.thread_layout)
        messages = [m for m in self._messages_cache if self._chip_match(m)]
        if not messages:
            self._append_empty("message_square", "No messages", self.thread_layout)
            return
        for m in messages:
            bubble = self._bubble(m)
            is_me = bool(m.get("is_from_me"))
            align = Qt.AlignmentFlag.AlignRight if is_me else Qt.AlignmentFlag.AlignLeft
            self.thread_layout.addWidget(bubble, 0, align)
        self.thread_layout.addStretch()

    def _chip_match(self, m: dict) -> bool:
        flt = self._active_filter
        if flt == "All":
            return True
        if flt == "Sent":
            return bool(m.get("is_from_me"))
        if flt == "Received":
            return not bool(m.get("is_from_me"))
        att = (m.get("attachment_type") or "").lower()
        text = m.get("text") or ""
        if flt == "Documents":
            return att == "document"
        if flt == "Media":
            return att in ("image", "video", "audio")
        if flt == "Links":
            return "http://" in text or "https://" in text
        return True

    def _bubble(self, m: dict) -> QLabel:
        text = m.get("text") or "(no text)"
        is_me = bool(m.get("is_from_me"))
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setMaximumWidth(360)
        lbl.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.MinimumExpanding,
        )
        lbl.setMinimumHeight(0)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if is_me:
            lbl.setStyleSheet(
                "background: #1B5E3B; color: #FFFFFF;"
                " padding: 6px 10px; font-size: 13px;"
            )
        else:
            lbl.setStyleSheet(
                "background: #FAFAF8; border: 1px solid #E8E8E2;"
                " padding: 6px 10px; font-size: 13px;"
            )
        return lbl

    def _do_search(self) -> None:
        q = self.search_box.input.text().strip()
        if not q:
            return
        self.thread_title.setText(f'Search: "{q}"')
        self._messages_cache = []
        self._active_filter = "All"
        for btn in self._chip_group.buttons():
            btn.setChecked(btn.text() == "All")
        self._clear_layout(self.thread_layout)
        loading = QLabel("Searching...")
        loading.setObjectName("mutedText")
        self.thread_layout.addWidget(loading)
        self.stack.setCurrentIndex(1)
        params = {"search": q, "limit": 100}
        if self._source:
            params["source"] = self._source
        api.run_async(
            api.get,
            on_result=self._on_messages,
            on_error=lambda msg: None,
            path=f"/analysis/evidence/{self.state.case_id}/messages",
            params=params,
        )

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _append_empty(self, icon_name: str, text: str, layout) -> None:
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, size=40, color="#98988F", stroke=1.5))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wl.addWidget(ic)
        lbl = QLabel(text)
        lbl.setObjectName("mutedText")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wl.addWidget(lbl)
        layout.addWidget(wrap)
        layout.addStretch()

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import api, icons
from ..format import fmt, fmt_time
from ..state import AppState
from ..touch import enable_touch_scroll

EVENT_COLORS = {
    "message": "#2A9461",
    "call": "#1565C0",
    "location": "#E65100",
    "web": "#6A1B9A",
}


class TimelinePage(QWidget):
    PAGE_SIZE = 100

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._events: list[dict] = []
        self._offset = 0
        self._total = 0
        self._loading_more = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel("Timeline")
        title.setStyleSheet(
            "font-size: 22px; font-weight: 800; background: transparent;"
        )
        top.addWidget(title)
        self.count_label = QLabel("0 events")
        self.count_label.setObjectName("mutedText")
        self.count_label.setStyleSheet(
            "background: transparent; padding-left: 8px;"
        )
        top.addWidget(self.count_label)
        top.addStretch(1)
        root.addLayout(top)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setObjectName("contentArea")
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        enable_touch_scroll(self.scroll)
        self.container = QFrame()
        self.container.setObjectName("card")
        self.container.setMinimumWidth(0)
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(10, 8, 10, 8)
        self.list_layout.setSpacing(0)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, 1)

        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scrolled)

        state.case_changed.connect(lambda _: self.refresh())

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        if not self.state.case_id:
            return
        self._events = []
        self._offset = 0
        self._total = 0
        self._loading_more = False
        self._clear_list()
        self._fetch_page()

    def _fetch_page(self) -> None:
        api.run_async(
            api.get,
            on_result=self._on_loaded,
            on_error=lambda _msg: None,
            path=f"/analysis/timeline/{self.state.case_id}",
            params={"limit": self.PAGE_SIZE, "offset": self._offset},
        )

    def _on_loaded(self, data) -> None:
        if isinstance(data, list):
            page = data
            self._total = max(self._total, self._offset + len(page))
        else:
            data = data or {}
            page = api.coerce_list(data, "events", "items", "timeline")
            self._total = int(data.get("total_events") or len(page) + self._offset)

        if self._offset == 0:
            self._events = []
            self._clear_list()

        self._events.extend(page)

        if not self._events:
            self._render_empty()
            return

        if (
            self.list_layout.count()
            and self.list_layout.itemAt(self.list_layout.count() - 1).spacerItem()
            is not None
        ):
            self.list_layout.takeAt(self.list_layout.count() - 1)
        for e in page:
            self.list_layout.addWidget(self._row(e))
        self.list_layout.addStretch()

        loaded = len(self._events)
        if loaded < self._total:
            self.count_label.setText(
                f"{fmt(loaded)} of {fmt(self._total)} events"
            )
        else:
            self.count_label.setText(f"{fmt(self._total)} events")

    def _load_more(self) -> None:
        self._offset += self.PAGE_SIZE
        api.run_async(
            api.get,
            on_result=self._on_more,
            on_error=lambda _msg: self._on_more(None),
            path=f"/analysis/timeline/{self.state.case_id}",
            params={"limit": self.PAGE_SIZE, "offset": self._offset},
        )

    def _on_more(self, data) -> None:
        self._loading_more = False
        self._on_loaded(data)

    def _on_scrolled(self, value: int) -> None:
        if self._loading_more:
            return
        sb = self.scroll.verticalScrollBar()
        max_val = sb.maximum()
        if max_val <= 0:
            return
        if value < max_val - 200:
            return
        if len(self._events) >= self._total:
            return
        self._loading_more = True
        self._load_more()

    def _render_empty(self) -> None:
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("clock", size=40, color="#98988F", stroke=1.5))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wl.addWidget(ic)
        msg = QLabel("No events")
        msg.setObjectName("mutedText")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wl.addWidget(msg)
        idx = max(self.list_layout.count() - 1, 0)
        self.list_layout.insertWidget(idx, wrap)
        if self.list_layout.itemAt(self.list_layout.count() - 1).spacerItem() is None:
            self.list_layout.addStretch()

    def _row(self, e: dict) -> QFrame:
        ev_type = e.get("event_type") or "message"
        color = EVENT_COLORS.get(ev_type, EVENT_COLORS["message"])

        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background: transparent; border-bottom: 1px solid #F0F0EA; }"
        )
        row = QHBoxLayout(frame)
        row.setContentsMargins(0, 8, 0, 8)
        row.setSpacing(12)

        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {color};")
        dot_wrap = QVBoxLayout()
        dot_wrap.setContentsMargins(0, 5, 0, 0)
        dot_wrap.addWidget(dot)
        dot_wrap.addStretch()
        row.addLayout(dot_wrap)

        col = QVBoxLayout()
        col.setSpacing(0)
        title = QLabel(e.get("title") or ev_type)
        title.setStyleSheet(
            "font-size: 13px; font-weight: 500; background: transparent;"
        )
        title.setWordWrap(True)
        col.addWidget(title)
        desc_text = e.get("description") or ""
        if desc_text:
            desc = QLabel(desc_text)
            desc.setObjectName("subtle")
            desc.setWordWrap(True)
            col.addWidget(desc)
        ts = QLabel(fmt_time(e.get("timestamp")))
        ts.setObjectName("monoSm")
        col.addWidget(ts)
        row.addLayout(col, 1)

        return frame

    def _clear_list(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.list_layout.addStretch()

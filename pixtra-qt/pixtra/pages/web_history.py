from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import api, icons
from ..format import fmt_time
from ..state import AppState
from ..touch import enable_touch_scroll


class WebHistoryPage(QWidget):
    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._load)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        search = QFrame()
        search.setStyleSheet("background: #FFFFFF; border: 1px solid #C8C8C0;")
        search.setFixedHeight(42)
        sl = QHBoxLayout(search)
        sl.setContentsMargins(12, 0, 12, 0)
        sl.setSpacing(8)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("search", size=16, color="#7A7A72"))
        sl.addWidget(ic)
        self.search_input = QLineEdit()
        self.search_input.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.search_input.setStyleSheet("border: none; background: transparent; font-size: 14px;")
        self.search_input.textChanged.connect(lambda _: self._debounce.start())
        sl.addWidget(self.search_input, 1)
        root.addWidget(search)

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
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(4, 4, 4, 4)
        self.list_layout.setSpacing(0)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, 1)

        state.case_changed.connect(lambda _: self._load())

    def on_show(self) -> None:
        self._load()

    def _load(self) -> None:
        if not self.state.case_id:
            return
        q = self.search_input.text().strip()
        params = {"search": q} if q and len(q) > 2 else None
        api.run_async(
            api.get,
            on_result=self._on_loaded,
            on_error=lambda msg: None,
            path=f"/analysis/evidence/{self.state.case_id}/web-history",
            params=params,
        )

    def _on_loaded(self, data) -> None:
        self._clear()
        entries = api.coerce_list(data, "entries", "items", "web_history", "history")
        if not entries:
            wrap = QWidget()
            wl = QVBoxLayout(wrap)
            wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ic = QLabel()
            ic.setPixmap(icons.pixmap("globe", size=40, color="#98988F", stroke=1.5))
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            wl.addWidget(ic)
            msg = QLabel("No web history")
            msg.setObjectName("mutedText")
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            wl.addWidget(msg)
            self.list_layout.addWidget(wrap)
            self.list_layout.addStretch()
            return

        for e in entries:
            self.list_layout.addWidget(self._row(e))
        self.list_layout.addStretch()

    def _row(self, e: dict) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background: transparent; border: none; border-bottom: 1px solid #F0F0EA; }"
        )
        col = QVBoxLayout(frame)
        col.setContentsMargins(10, 8, 10, 8)
        col.setSpacing(1)

        title = QLabel(e.get("title") or "Untitled")
        title.setStyleSheet("font-size: 13px; font-weight: 500; background: transparent;")
        title.setWordWrap(True)
        title.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        title.setMinimumHeight(0)
        col.addWidget(title)

        url = QLabel(e.get("url") or "")
        url.setObjectName("monoSm")
        url.setStyleSheet("color: #1B5E3B; font-family: 'JetBrains Mono','Consolas',monospace; font-size: 11px;")
        url.setWordWrap(True)
        url.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        url.setMinimumHeight(0)
        col.addWidget(url)

        meta_parts = [fmt_time(e.get("timestamp"))]
        if e.get("visit_count") and e.get("visit_count") > 1:
            meta_parts.append(f"{e['visit_count']} visits")
        if e.get("search_term"):
            meta_parts.append(f'"{e["search_term"]}"')
        meta = QLabel(" · ".join(meta_parts))
        meta.setObjectName("subtle")
        col.addWidget(meta)

        return frame

    def _clear(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

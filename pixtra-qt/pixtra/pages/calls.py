from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import api, icons
from ..format import fmt_duration, fmt_time
from ..state import AppState
from ..touch import enable_touch_scroll


FILTERS = [("all", "All"), ("incoming", "Incoming"), ("outgoing", "Outgoing"), ("missed", "Missed")]


class CallsPage(QWidget):
    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._filter = "all"

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        seg = QFrame()
        seg.setObjectName("segGroup")
        sg = QHBoxLayout(seg)
        sg.setContentsMargins(2, 2, 2, 2)
        sg.setSpacing(2)
        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)
        for idx, (key, label) in enumerate(FILTERS):
            btn = QPushButton(label)
            btn.setObjectName("segBtn")
            btn.setCheckable(True)
            if idx == 0:
                btn.setChecked(True)
            btn.clicked.connect(lambda _=False, k=key: self._set_filter(k))
            sg.addWidget(btn)
            self._btn_group.addButton(btn)
        root.addWidget(seg)

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

        state.case_changed.connect(lambda _: self._load())

    def on_show(self) -> None:
        self._load()

    def _set_filter(self, key: str) -> None:
        if key == self._filter:
            return
        self._filter = key
        self._load()

    def _load(self) -> None:
        if not self.state.case_id:
            return
        path = f"/analysis/evidence/{self.state.case_id}/calls"
        params = None if self._filter == "all" else {"direction": self._filter}
        api.run_async(
            api.get,
            on_result=self._on_loaded,
            on_error=lambda msg: None,
            path=path,
            params=params,
        )

    def _on_loaded(self, data) -> None:
        self._clear()
        calls = api.coerce_list(data, "calls", "items")
        if not calls:
            self._append_empty()
            return
        for c in calls:
            self.list_layout.addWidget(self._row(c))
        self.list_layout.addStretch()

    def _row(self, c: dict) -> QFrame:
        direction = c.get("direction") or "outgoing"
        if direction == "incoming":
            icon_name, bg, fg = "arrow_down_left", "#D4EDDF", "#14432A"
        elif direction == "outgoing":
            icon_name, bg, fg = "arrow_up_right", "#EAEAE4", "#62625F"
        else:
            icon_name, bg, fg = "phone_missed", "#FDECEA", "#C62828"

        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #FFFFFF; border-bottom: 1px solid #E8E8E2; }")
        row = QHBoxLayout(frame)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)

        av = QLabel()
        av.setFixedSize(34, 34)
        av.setAlignment(Qt.AlignmentFlag.AlignCenter)
        av.setStyleSheet(f"background: {bg};")
        av.setPixmap(icons.pixmap(icon_name, size=18, color=fg, stroke=2.25))
        row.addWidget(av)

        mid = QVBoxLayout()
        mid.setSpacing(0)
        name = QLabel(c.get("name") or c.get("number") or "Unknown")
        name.setStyleSheet("font-size: 13px; font-weight: 600; background: transparent;")
        name.setWordWrap(True)
        mid.addWidget(name)
        sub_parts = []
        if c.get("number"):
            sub_parts.append(c["number"])
        if c.get("duration_seconds"):
            sub_parts.append(fmt_duration(c["duration_seconds"]))
        sub = QLabel(" · ".join(sub_parts))
        sub.setObjectName("monoSm")
        sub.setWordWrap(True)
        mid.addWidget(sub)
        row.addLayout(mid, 1)

        right = QVBoxLayout()
        right.setAlignment(Qt.AlignmentFlag.AlignRight)
        ts = QLabel(fmt_time(c.get("timestamp")))
        ts.setObjectName("subtle")
        ts.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addWidget(ts)
        badge = QLabel(direction)
        if direction == "missed":
            badge.setObjectName("badgeRed")
        elif direction == "incoming":
            badge.setObjectName("badgeGreen")
        else:
            badge.setObjectName("badgeGray")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(badge)
        row.addLayout(right)

        return frame

    def _append_empty(self) -> None:
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("phone", size=40, color="#98988F", stroke=1.5))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wl.addWidget(ic)
        msg = QLabel("No calls")
        msg.setObjectName("mutedText")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wl.addWidget(msg)
        self.list_layout.addWidget(wrap)
        self.list_layout.addStretch()

    def _clear(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

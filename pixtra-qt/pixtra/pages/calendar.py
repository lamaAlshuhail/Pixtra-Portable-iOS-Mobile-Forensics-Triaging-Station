from __future__ import annotations

from datetime import datetime
from typing import Optional

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QMouseEvent, QPainter, QPixmap
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

from .. import api, icons
from ..format import fmt
from ..state import AppState
from ..theme import GREEN_700, apply_card_shadow
from ..touch import enable_touch_scroll


def _fmt_event_dt(iso: Optional[str], all_day: bool) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso
    if all_day:
        try:
            return dt.strftime("%a %b %-d")
        except ValueError:
            return dt.strftime("%a %b %d")
    try:
        return dt.strftime("%a %b %-d · %-I:%M %p")
    except ValueError:
        return dt.strftime("%a %b %d · %I:%M %p")


def _fmt_short_date(iso: Optional[str]) -> str:
    if not iso:
        return " - "
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return iso[:10] or " - "


def _fmt_duration(start_iso: Optional[str], end_iso: Optional[str], all_day: bool) -> str:
    if all_day:
        return "all day"
    if not start_iso or not end_iso:
        return ""
    try:
        sd = datetime.fromisoformat(start_iso)
        ed = datetime.fromisoformat(end_iso)
    except (TypeError, ValueError):
        return ""
    secs = (ed - sd).total_seconds()
    if secs <= 0:
        return ""
    mins = int(round(secs / 60))
    if mins < 60:
        return f"{mins} min"
    hours = mins / 60
    if hours < 24:
        h = int(hours)
        m = int(mins - h * 60)
        return f"{h}h {m}m" if m else f"{h}h"
    days = hours / 24
    d = int(days)
    return f"{d}d"


def _dot_pixmap(color_hex: Optional[str], diameter: int = 10) -> QPixmap:
    pix = QPixmap(diameter, diameter)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color_hex or "#888888"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(0, 0, diameter, diameter)
    painter.end()
    return pix


class _EventRow(QFrame):

    clicked = pyqtSignal(dict)

    def __init__(self, ev: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._event = ev
        self.setObjectName("caseCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        band = QFrame()
        band.setFixedWidth(4)
        color = ev.get("calendar_color") or GREEN_700
        band.setStyleSheet(f"background: {color};")
        row.addWidget(band)

        body = QHBoxLayout()
        body.setContentsMargins(12, 8, 12, 8)
        body.setSpacing(10)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        line1 = QHBoxLayout()
        line1.setSpacing(8)
        summary = QLabel(ev.get("summary") or "(untitled)")
        summary.setStyleSheet(
            "font-size: 13px; font-weight: 600; background: transparent;"
        )
        summary.setWordWrap(True)
        summary.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        summary.setMinimumHeight(0)
        line1.addWidget(summary, 1)

        time_lbl = QLabel(_fmt_event_dt(ev.get("start"), bool(ev.get("all_day"))))
        time_lbl.setObjectName("monoSm")
        time_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        time_lbl.setFixedWidth(140)
        time_lbl.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
        )
        line1.addWidget(time_lbl)
        text_col.addLayout(line1)

        line2 = QHBoxLayout()
        line2.setSpacing(8)
        meta_parts = [ev.get("calendar_title") or "(no calendar)"]
        if ev.get("location_title"):
            meta_parts.append(str(ev["location_title"]))
        meta = QLabel(" · ".join(meta_parts))
        meta.setStyleSheet(
            "font-size: 12px; color: #888888; background: transparent;"
        )
        meta.setWordWrap(True)
        meta.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        meta.setMinimumHeight(0)
        line2.addWidget(meta, 1)

        right_wrap = QHBoxLayout()
        right_wrap.setContentsMargins(0, 0, 0, 0)
        right_wrap.setSpacing(4)
        if ev.get("has_recurrences"):
            rec_lbl = QLabel()
            rec_lbl.setPixmap(icons.pixmap("refresh", size=10, color="#888888"))
            rec_lbl.setToolTip("Recurring event")
            right_wrap.addWidget(rec_lbl)
        right_wrap.addStretch(1)
        dur_lbl = QLabel(
            _fmt_duration(ev.get("start"), ev.get("end"), bool(ev.get("all_day")))
        )
        dur_lbl.setObjectName("monoSm")
        dur_lbl.setStyleSheet(
            "font-size: 11px; color: #888888; background: transparent;"
        )
        dur_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        right_wrap.addWidget(dur_lbl)
        right_wrap_widget = QWidget()
        right_wrap_widget.setLayout(right_wrap)
        right_wrap_widget.setFixedWidth(140)
        right_wrap_widget.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
        )
        line2.addWidget(right_wrap_widget)
        text_col.addLayout(line2)

        body.addLayout(text_col, 1)
        row.addLayout(body, 1)
        apply_card_shadow(self)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._event)
        super().mousePressEvent(e)


class CalendarPage(QWidget):
    navigate_requested = pyqtSignal(str)

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._events: list[dict] = []
        self._calendars: list[dict] = []
        self._calendar_filter: Optional[int] = None
        self._search: str = ""
        self._chip_buttons: list[QPushButton] = []

        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(300)
        self._search_debounce.timeout.connect(self._fetch_events)

        self.stack = QStackedWidget(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.stack)

        self.stack.addWidget(self._build_browser_view())
        self.stack.addWidget(self._build_detail_view())

        state.case_changed.connect(lambda _: self.refresh())

    def on_show(self) -> None:
        self.refresh()

    @staticmethod
    def _build_stat_card(label: str, value: str = " - ") -> tuple[QFrame, QLabel]:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background: #FFFFFF; border: 1px solid #E8E8E2; "
            f"border-left: 4px solid {GREEN_700}; border-radius: 8px; }}"
        )
        frame.setFixedHeight(52)
        col = QVBoxLayout(frame)
        col.setContentsMargins(10, 6, 10, 6)
        col.setSpacing(2)
        lbl_label = QLabel(label)
        lbl_label.setStyleSheet(
            "font-size: 11px; color: #666666; background: transparent; "
            "border: none;"
        )
        col.addWidget(lbl_label)
        lbl_value = QLabel(value)
        lbl_value.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #222222; "
            "background: transparent; border: none;"
        )
        lbl_value.setWordWrap(True)
        col.addWidget(lbl_value)
        return frame, lbl_value

    def _build_browser_view(self) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(8, 6, 8, 8)
        col.setSpacing(6)

        row_a = QHBoxLayout()
        row_a.setSpacing(8)
        title = QLabel("Calendar")
        title.setStyleSheet(
            "font-size: 20px; font-weight: 800; background: transparent;"
        )
        row_a.addWidget(title)
        self.count_label = QLabel("0 events")
        self.count_label.setObjectName("mutedText")
        self.count_label.setStyleSheet(
            "background: transparent; padding-left: 4px;"
        )
        row_a.addWidget(self.count_label)
        row_a.addStretch(1)

        search_box = QFrame()
        search_box.setStyleSheet(
            "background: #FFFFFF; border: 1px solid #C8C8C0; border-radius: 6px;"
        )
        search_box.setFixedHeight(36)
        search_box.setMaximumWidth(320)
        sl = QHBoxLayout(search_box)
        sl.setContentsMargins(10, 0, 10, 0)
        sl.setSpacing(6)
        sicon = QLabel()
        sicon.setPixmap(icons.pixmap("search", size=14, color="#7A7A72"))
        sl.addWidget(sicon)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search events…")
        self.search_input.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.search_input.setStyleSheet(
            "border: none; background: transparent; font-size: 12px;"
        )
        self.search_input.textChanged.connect(self._on_search_changed)
        sl.addWidget(self.search_input, 1)
        row_a.addWidget(search_box)
        col.addLayout(row_a)

        stats = QHBoxLayout()
        stats.setSpacing(8)
        self._stat_dates_frame, self._stat_dates_value = self._build_stat_card(
            "Date range"
        )
        self._stat_busiest_frame, self._stat_busiest_value = self._build_stat_card(
            "Busiest calendar"
        )
        self._stat_active_frame, self._stat_active_value = self._build_stat_card(
            "Calendars"
        )
        stats.addWidget(self._stat_dates_frame, 1)
        stats.addWidget(self._stat_busiest_frame, 1)
        stats.addWidget(self._stat_active_frame, 1)
        col.addLayout(stats)

        self.chips_scroll = QScrollArea()
        self.chips_scroll.setWidgetResizable(True)
        self.chips_scroll.setFixedHeight(36)
        self.chips_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.chips_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.chips_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.chips_scroll.setStyleSheet("background: transparent;")
        self.chips_host = QWidget()
        self.chips_row = QHBoxLayout(self.chips_host)
        self.chips_row.setContentsMargins(0, 2, 0, 2)
        self.chips_row.setSpacing(6)
        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)
        self.chips_row.addStretch(1)
        self.chips_scroll.setWidget(self.chips_host)
        col.addWidget(self.chips_scroll)

        self.list_scroll = QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.list_scroll.setObjectName("contentArea")
        self.list_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        enable_touch_scroll(self.list_scroll)
        self.list_host = QWidget()
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch(1)
        self.list_scroll.setWidget(self.list_host)
        col.addWidget(self.list_scroll, 1)

        def _sync_host_width() -> None:
            self.list_host.setMaximumWidth(self.list_scroll.viewport().width())

        original_resize = self.list_scroll.resizeEvent

        def _patched_resize(event):
            original_resize(event)
            _sync_host_width()

        self.list_scroll.resizeEvent = _patched_resize
        _sync_host_width()

        return page

    def _build_detail_view(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)

        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.detail_scroll.setObjectName("contentArea")
        self.detail_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        enable_touch_scroll(self.detail_scroll)

        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(8, 8, 8, 8)
        col.setSpacing(8)

        back_btn = QPushButton("  Back")
        back_btn.setObjectName("btnGhost")
        back_btn.setIcon(icons.qicon("chevron_left", size=14, color="#62625F"))
        back_btn.setIconSize(icons.icon_size(14))
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        col.addWidget(back_btn, 0, Qt.AlignmentFlag.AlignLeft)

        header = QFrame()
        header.setObjectName("roundCard")
        apply_card_shadow(header)
        hl = QVBoxLayout(header)
        hl.setContentsMargins(14, 12, 14, 12)
        hl.setSpacing(4)
        self.detail_summary = QLabel("")
        self.detail_summary.setStyleSheet(
            "font-size: 16px; font-weight: 700; background: transparent;"
        )
        self.detail_summary.setWordWrap(True)
        hl.addWidget(self.detail_summary)
        self.detail_calendar = QLabel("")
        self.detail_calendar.setObjectName("mutedText")
        hl.addWidget(self.detail_calendar)
        self.detail_when = QLabel("")
        self.detail_when.setObjectName("subtle")
        self.detail_when.setWordWrap(True)
        hl.addWidget(self.detail_when)
        col.addWidget(header)

        self.detail_desc_frame = QFrame()
        self.detail_desc_frame.setObjectName("roundCard")
        apply_card_shadow(self.detail_desc_frame)
        df = QVBoxLayout(self.detail_desc_frame)
        df.setContentsMargins(14, 12, 14, 12)
        df.setSpacing(4)
        desc_title = QLabel("Description")
        desc_title.setStyleSheet(
            f"color: {GREEN_700}; font-size: 12px; font-weight: 700; "
            f"letter-spacing: 0.5px; background: transparent;"
        )
        df.addWidget(desc_title)
        self.detail_description = QLabel("")
        self.detail_description.setWordWrap(True)
        self.detail_description.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        df.addWidget(self.detail_description)
        col.addWidget(self.detail_desc_frame)

        self.detail_loc_frame = QFrame()
        self.detail_loc_frame.setObjectName("roundCard")
        apply_card_shadow(self.detail_loc_frame)
        lf = QVBoxLayout(self.detail_loc_frame)
        lf.setContentsMargins(14, 12, 14, 12)
        lf.setSpacing(4)
        loc_title = QLabel("Location")
        loc_title.setStyleSheet(
            f"color: {GREEN_700}; font-size: 12px; font-weight: 700; "
            f"letter-spacing: 0.5px; background: transparent;"
        )
        lf.addWidget(loc_title)
        self.detail_location = QLabel("")
        self.detail_location.setWordWrap(True)
        self.detail_location.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        lf.addWidget(self.detail_location)
        col.addWidget(self.detail_loc_frame)

        meta = QFrame()
        meta.setObjectName("roundCard")
        apply_card_shadow(meta)
        mf = QVBoxLayout(meta)
        mf.setContentsMargins(14, 12, 14, 12)
        mf.setSpacing(4)
        meta_title = QLabel("Forensic reference")
        meta_title.setStyleSheet(
            f"color: {GREEN_700}; font-size: 12px; font-weight: 700; "
            f"letter-spacing: 0.5px; background: transparent;"
        )
        mf.addWidget(meta_title)
        self.detail_meta_status = QLabel("")
        self.detail_meta_status.setObjectName("monoSm")
        mf.addWidget(self.detail_meta_status)
        self.detail_meta_recur = QLabel("")
        self.detail_meta_recur.setObjectName("monoSm")
        mf.addWidget(self.detail_meta_recur)
        self.detail_meta_account = QLabel("")
        self.detail_meta_account.setObjectName("monoSm")
        self.detail_meta_account.setWordWrap(True)
        self.detail_meta_account.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        mf.addWidget(self.detail_meta_account)
        self.detail_meta_uuid = QLabel("")
        self.detail_meta_uuid.setStyleSheet(
            "font-family: 'JetBrains Mono','Consolas',monospace; font-size: 11px; "
            "background: transparent;"
        )
        self.detail_meta_uuid.setWordWrap(True)
        self.detail_meta_uuid.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        mf.addWidget(self.detail_meta_uuid)
        self.detail_meta_created = QLabel("")
        self.detail_meta_created.setObjectName("monoSm")
        mf.addWidget(self.detail_meta_created)
        self.detail_meta_modified = QLabel("")
        self.detail_meta_modified.setObjectName("monoSm")
        mf.addWidget(self.detail_meta_modified)
        col.addWidget(meta)

        col.addStretch(1)

        self.detail_scroll.setWidget(inner)
        outer.addWidget(self.detail_scroll)
        return page

    def refresh(self) -> None:
        if not self.state.case_id:
            return
        self._render_status("Loading calendar…")
        self._fetch_events()

    def _on_search_changed(self, text: str) -> None:
        self._search = (text or "").strip()
        self._search_debounce.start()

    def _fetch_events(self) -> None:
        if not self.state.case_id:
            return
        params: dict = {}
        if self._search and len(self._search) > 1:
            params["search"] = self._search
        if self._calendar_filter is not None:
            params["calendar_id"] = self._calendar_filter
        api.run_async(
            api.get,
            on_result=self._on_loaded,
            on_error=lambda msg: self._render_status(f"Failed to load: {msg}"),
            path=f"/analysis/evidence/{self.state.case_id}/calendar-events",
            params=params or None,
        )

    def _on_loaded(self, data) -> None:
        if not isinstance(data, dict):
            self._events = []
            self._calendars = []
            self._render_status("Unexpected response")
            return
        self._events = list(data.get("events") or [])
        new_cals = list(data.get("calendars") or [])
        if not self._calendars or len(new_cals) != len(self._calendars):
            self._calendars = new_cals
            self._rebuild_chips()
        else:
            self._calendars = new_cals
        self._update_stats(data.get("stats") or {})
        self._render_list()

    def _update_stats(self, stats: dict) -> None:
        date_range = stats.get("date_range") or {}
        earliest = _fmt_short_date(date_range.get("earliest"))
        latest = _fmt_short_date(date_range.get("latest"))
        if earliest == latest:
            self._stat_dates_value.setText(earliest)
        else:
            self._stat_dates_value.setText(f"{earliest} → {latest}")

        by_cal = stats.get("by_calendar") or {}
        if by_cal:
            top_name, top_n = max(by_cal.items(), key=lambda kv: int(kv[1] or 0))
            self._stat_busiest_value.setText(
                f"{top_name} ({fmt(int(top_n))})"
            )
        else:
            self._stat_busiest_value.setText(" - ")

        self._stat_active_value.setText(
            f"{len(self._calendars)} active" if self._calendars else "0"
        )

    def _rebuild_chips(self) -> None:
        for btn in self._chip_buttons:
            self._chip_group.removeButton(btn)
            btn.setParent(None)
            btn.deleteLater()
        self._chip_buttons = []

        all_btn = QPushButton("All")
        all_btn.setObjectName("chipFilter")
        all_btn.setCheckable(True)
        all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        all_btn.setChecked(True)
        all_btn.clicked.connect(lambda _checked: self._set_calendar_filter(None))
        self._chip_group.addButton(all_btn)
        self.chips_row.insertWidget(self.chips_row.count() - 1, all_btn)
        self._chip_buttons.append(all_btn)

        for cal in self._calendars:
            label = f"{cal.get('title') or '(unnamed)'}  {fmt(int(cal.get('event_count') or 0))}"
            btn = QPushButton(label)
            btn.setObjectName("chipFilter")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIcon(QIcon(_dot_pixmap(cal.get("color_hex"), 10)))
            btn.setIconSize(QSize(10, 10))
            cal_id = cal.get("id")
            btn.clicked.connect(
                lambda _checked, cid=cal_id: self._set_calendar_filter(cid)
            )
            self._chip_group.addButton(btn)
            self.chips_row.insertWidget(self.chips_row.count() - 1, btn)
            self._chip_buttons.append(btn)

    def _set_calendar_filter(self, cal_id: Optional[int]) -> None:
        self._calendar_filter = cal_id
        self._fetch_events()

    def _render_list(self) -> None:
        self._clear_list()
        n = len(self._events)
        self.count_label.setText(f"{fmt(n)} events" if n != 1 else "1 event")

        if not self._events:
            self._render_status(
                "No events match" if self._search else "No calendar events"
            )
            return

        for ev in self._events:
            row = _EventRow(ev)
            row.clicked.connect(self._open_detail)
            self.list_layout.insertWidget(self.list_layout.count() - 1, row)

    def _render_status(self, message: str) -> None:
        self._clear_list()
        lbl = QLabel(message)
        lbl.setObjectName("mutedText")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("background: transparent; padding: 32px 0;")
        self.list_layout.insertWidget(self.list_layout.count() - 1, lbl)

    def _clear_list(self) -> None:
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _open_detail(self, ev: dict) -> None:
        self.detail_summary.setText(ev.get("summary") or "(untitled)")
        cal_title = ev.get("calendar_title") or "(no calendar)"
        self.detail_calendar.setText(cal_title)
        all_day = bool(ev.get("all_day"))
        when_parts = []
        when_parts.append(_fmt_event_dt(ev.get("start"), all_day))
        end_str = _fmt_event_dt(ev.get("end"), all_day)
        if end_str and end_str != when_parts[0]:
            when_parts.append(f"→ {end_str}")
        if all_day:
            when_parts.append("(all day)")
        self.detail_when.setText("  ".join(p for p in when_parts if p))

        desc = (ev.get("description") or "").strip()
        if desc:
            self.detail_desc_frame.setVisible(True)
            self.detail_description.setText(desc)
        else:
            self.detail_desc_frame.setVisible(False)

        loc_parts = []
        if ev.get("location_title"):
            loc_parts.append(str(ev["location_title"]))
        if ev.get("location_lat") is not None and ev.get("location_lng") is not None:
            try:
                loc_parts.append(
                    f"{float(ev['location_lat']):.5f}, "
                    f"{float(ev['location_lng']):.5f}"
                )
            except (TypeError, ValueError):
                pass
        if loc_parts:
            self.detail_loc_frame.setVisible(True)
            self.detail_location.setText(" · ".join(loc_parts))
        else:
            self.detail_loc_frame.setVisible(False)

        status = ev.get("status")
        self.detail_meta_status.setText(
            f"Status: {status if status is not None else ' - '}"
        )
        self.detail_meta_recur.setText(
            "Recurring event" if ev.get("has_recurrences") else "Single occurrence"
        )

        account = " - "
        for cal in self._calendars:
            if cal.get("title") == ev.get("calendar_title"):
                account = cal.get("account") or " - "
                break
        self.detail_meta_account.setText(f"Calendar account: {account}")

        uuid_val = ev.get("uuid") or " - "
        self.detail_meta_uuid.setText(f"UUID: {uuid_val}")

        created = ev.get("created")
        modified = ev.get("last_modified")
        self.detail_meta_created.setText(
            f"Created: {created or ' - '}"
        )
        self.detail_meta_modified.setText(
            f"Last modified: {modified or ' - '}"
        )

        self.stack.setCurrentIndex(1)

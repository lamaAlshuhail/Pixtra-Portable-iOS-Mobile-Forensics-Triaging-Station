from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import api, icons
from ..format import fmt, fmt_bytes
from ..state import AppState
from ..theme import GREEN_700, apply_card_shadow
from ..touch import enable_touch_scroll


_CHIPS: list[tuple[str, str, object]] = [
    ("All", "_all", None),
    ("Active", "archived", 0),
    ("Archived", "archived", 1),
    ("Don't remember", "_dnr", True),
    ("Temporary", "_temp", True),
]


def _fmt_compact_date(iso: Optional[str]) -> str:
    if not iso:
        return " - "
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return iso[:10] or " - "


def _fmt_year_month(iso: Optional[str]) -> str:
    if not iso:
        return " - "
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m")
    except (TypeError, ValueError):
        return iso[:7] or " - "


def _fmt_message_dt(iso: Optional[str]) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return iso


class _ConvRow(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, conv: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._conv = conv
        self.setObjectName("caseCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(12)

        ic = QLabel()
        ic.setFixedSize(32, 32)
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic.setPixmap(icons.pixmap("message_circle", size=20, color=GREEN_700))
        ic.setStyleSheet("background: transparent;")
        row.addWidget(ic)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        line1 = QHBoxLayout()
        line1.setSpacing(8)
        title = QLabel(conv.get("title") or "(untitled)")
        title.setStyleSheet(
            "font-size: 14px; font-weight: 600; background: transparent;"
        )
        title.setWordWrap(True)
        title.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        title.setMinimumHeight(0)
        line1.addWidget(title, 1)

        last = QLabel(_fmt_compact_date(conv.get("modification_date")))
        last.setObjectName("monoSm")
        last.setStyleSheet(
            "font-size: 11px; color: #1C1C1A; background: transparent;"
        )
        last.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        last.setFixedWidth(96)
        last.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
        )
        line1.addWidget(last)
        text_col.addLayout(line1)

        line2 = QHBoxLayout()
        line2.setSpacing(8)
        sub_parts = []
        n = int(conv.get("message_count") or 0)
        sub_parts.append(f"{fmt(n)} message" + ("" if n == 1 else "s"))
        if conv.get("default_model"):
            sub_parts.append(str(conv["default_model"]))
        sub = QLabel(" · ".join(sub_parts))
        sub.setStyleSheet(
            "font-size: 11px; color: #888888; background: transparent;"
        )
        sub.setWordWrap(True)
        sub.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        sub.setMinimumHeight(0)
        line2.addWidget(sub, 1)

        created = QLabel(f"created {_fmt_compact_date(conv.get('creation_date'))}")
        created.setStyleSheet(
            "font-size: 11px; color: #888888; background: transparent;"
        )
        created.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        created.setFixedWidth(160)
        created.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
        )
        line2.addWidget(created)
        text_col.addLayout(line2)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)
        chips_row.setContentsMargins(0, 0, 0, 0)
        if conv.get("is_temporary_chat"):
            chips_row.addWidget(self._mini_chip("Temporary", "#E65100", "#FFF3E0"))
        if conv.get("is_do_not_remember"):
            chips_row.addWidget(self._mini_chip("Don't remember", "#C62828", "#FDECEA"))
        if conv.get("is_archived"):
            chips_row.addWidget(self._mini_chip("Archived", "#555555", "#EAEAE4"))
        chips_row.addStretch(1)
        if (
            conv.get("is_temporary_chat")
            or conv.get("is_do_not_remember")
            or conv.get("is_archived")
        ):
            text_col.addLayout(chips_row)

        row.addLayout(text_col, 1)

        if conv.get("is_archived"):
            self.setStyleSheet("QFrame#caseCard { color: #666666; }")
        apply_card_shadow(self)

    @staticmethod
    def _mini_chip(text: str, fg: str, bg: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"QLabel {{ background: {bg}; color: {fg}; font-size: 10px; "
            f"font-weight: 600; padding: 2px 6px; border-radius: 8px; }}"
        )
        return lbl

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._conv)
        super().mousePressEvent(e)


class AIConversationsPage(QWidget):
    navigate_requested = pyqtSignal(str)

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._all_convs: list[dict] = []
        self._stats: dict = {}
        self._chip_value: tuple[str, object] = ("_all", None)
        self._search: str = ""

        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(300)
        self._search_debounce.timeout.connect(self._fetch)

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
            "font-size: 10px; color: #666666; background: transparent; "
            "border: none;"
        )
        col.addWidget(lbl_label)
        lbl_value = QLabel(value)
        lbl_value.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: #222222; "
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

        top = QHBoxLayout()
        top.setSpacing(8)
        title = QLabel("AI Chats")
        title.setStyleSheet(
            "font-size: 20px; font-weight: 800; background: transparent;"
        )
        top.addWidget(title)
        self.count_label = QLabel("0 conversations")
        self.count_label.setObjectName("mutedText")
        self.count_label.setStyleSheet(
            "background: transparent; padding-left: 4px;"
        )
        top.addWidget(self.count_label)
        top.addStretch(1)

        search_box = QFrame()
        search_box.setStyleSheet(
            "background: #FFFFFF; border: 1px solid #C8C8C0; border-radius: 6px;"
        )
        search_box.setFixedHeight(36)
        search_box.setMaximumWidth(280)
        sl = QHBoxLayout(search_box)
        sl.setContentsMargins(10, 0, 10, 0)
        sl.setSpacing(6)
        sicon = QLabel()
        sicon.setPixmap(icons.pixmap("search", size=14, color="#7A7A72"))
        sl.addWidget(sicon)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search titles…")
        self.search_input.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.search_input.setStyleSheet(
            "border: none; background: transparent; font-size: 12px;"
        )
        self.search_input.textChanged.connect(self._on_search_changed)
        sl.addWidget(self.search_input, 1)
        top.addWidget(search_box)
        col.addLayout(top)

        stats = QHBoxLayout()
        stats.setSpacing(8)
        self._stat_account_frame, self._stat_account_value = self._build_stat_card(
            "ChatGPT account"
        )
        self._stat_count_frame, self._stat_count_value = self._build_stat_card(
            "Volume"
        )
        self._stat_range_frame, self._stat_range_value = self._build_stat_card(
            "Date range"
        )
        stats.addWidget(self._stat_account_frame, 1)
        stats.addWidget(self._stat_count_frame, 1)
        stats.addWidget(self._stat_range_frame, 1)
        col.addLayout(stats)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)
        for label, key, value in _CHIPS:
            btn = QPushButton(label)
            btn.setObjectName("chipFilter")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if key == "_all":
                btn.setChecked(True)
            btn.clicked.connect(
                lambda _checked, k=key, v=value: self._set_chip(k, v)
            )
            self._chip_group.addButton(btn)
            chips.addWidget(btn)
        chips.addStretch(1)
        col.addLayout(chips)

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
        self.detail_title = QLabel("")
        self.detail_title.setStyleSheet(
            "font-size: 16px; font-weight: 700; background: transparent;"
        )
        self.detail_title.setWordWrap(True)
        hl.addWidget(self.detail_title)
        self.detail_dates = QLabel("")
        self.detail_dates.setObjectName("subtle")
        self.detail_dates.setWordWrap(True)
        hl.addWidget(self.detail_dates)
        self.detail_account = QLabel("")
        self.detail_account.setStyleSheet(
            "font-family: 'JetBrains Mono','Consolas',monospace; font-size: 11px; "
            "color: #888888; background: transparent;"
        )
        self.detail_account.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.detail_account.setWordWrap(True)
        hl.addWidget(self.detail_account)
        self.detail_flags_row = QHBoxLayout()
        self.detail_flags_row.setSpacing(6)
        self.detail_flags_row.setContentsMargins(0, 4, 0, 0)
        self.detail_flags_row.addStretch(1)
        flags_wrap = QWidget()
        flags_wrap.setLayout(self.detail_flags_row)
        hl.addWidget(flags_wrap)
        col.addWidget(header)

        self.detail_ci_frame = QFrame()
        self.detail_ci_frame.setObjectName("roundCard")
        apply_card_shadow(self.detail_ci_frame)
        cf = QVBoxLayout(self.detail_ci_frame)
        cf.setContentsMargins(14, 12, 14, 12)
        cf.setSpacing(6)
        cf_title = QLabel("Custom instructions")
        cf_title.setStyleSheet(
            f"color: {GREEN_700}; font-size: 12px; font-weight: 700; "
            f"letter-spacing: 0.5px; background: transparent;"
        )
        cf.addWidget(cf_title)
        self.detail_ci_user_label = QLabel("About user")
        self.detail_ci_user_label.setObjectName("formLabel")
        cf.addWidget(self.detail_ci_user_label)
        self.detail_ci_user = QLabel("")
        self.detail_ci_user.setStyleSheet(
            "font-family: 'JetBrains Mono','Consolas',monospace; font-size: 11px; "
            "background: #FAFAF7; padding: 8px; border: 1px solid #E8E8E2;"
        )
        self.detail_ci_user.setWordWrap(True)
        self.detail_ci_user.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        cf.addWidget(self.detail_ci_user)
        self.detail_ci_model_label = QLabel("About model")
        self.detail_ci_model_label.setObjectName("formLabel")
        cf.addWidget(self.detail_ci_model_label)
        self.detail_ci_model = QLabel("")
        self.detail_ci_model.setStyleSheet(
            "font-family: 'JetBrains Mono','Consolas',monospace; font-size: 11px; "
            "background: #FAFAF7; padding: 8px; border: 1px solid #E8E8E2;"
        )
        self.detail_ci_model.setWordWrap(True)
        self.detail_ci_model.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        cf.addWidget(self.detail_ci_model)
        col.addWidget(self.detail_ci_frame)

        self.detail_tabs = QTabWidget()
        self.detail_tabs.setStyleSheet(
            "QTabWidget::pane { border: none; background: transparent; }"
            "QTabBar::tab {"
            " background: #EAEAE4; color: #555555;"
            " padding: 6px 18px; margin-right: 4px;"
            " border-top-left-radius: 6px; border-top-right-radius: 6px;"
            " font-size: 12px; font-weight: 600;"
            "}"
            f"QTabBar::tab:selected {{ background: {GREEN_700}; color: #FFFFFF; }}"
        )

        rendered_tab = QWidget()
        self.detail_thread_layout = QVBoxLayout(rendered_tab)
        self.detail_thread_layout.setContentsMargins(0, 8, 0, 8)
        self.detail_thread_layout.setSpacing(8)
        self.detail_tabs.addTab(rendered_tab, "Rendered")

        metadata_tab = QWidget()
        self.detail_metadata_layout = QVBoxLayout(metadata_tab)
        self.detail_metadata_layout.setContentsMargins(0, 8, 0, 8)
        self.detail_metadata_layout.setSpacing(8)
        self.detail_tabs.addTab(metadata_tab, "Metadata")

        col.addWidget(self.detail_tabs, 1)
        col.addStretch(1)

        self.detail_scroll.setWidget(inner)
        outer.addWidget(self.detail_scroll)
        return page

    def refresh(self) -> None:
        if not self.state.case_id:
            return
        self._render_status("Loading conversations…")
        self._fetch()

    def _on_search_changed(self, text: str) -> None:
        self._search = (text or "").strip()
        self._search_debounce.start()

    def _set_chip(self, key: str, value: object) -> None:
        self._chip_value = (key, value)
        self._render_list()

    def _fetch(self) -> None:
        if not self.state.case_id:
            return
        params: dict = {}
        if self._search and len(self._search) > 1:
            params["search"] = self._search
        api.run_async(
            api.get,
            on_result=self._on_loaded,
            on_error=lambda msg: self._render_status(f"Failed to load: {msg}"),
            path=f"/analysis/evidence/{self.state.case_id}/ai-conversations",
            params=params or None,
        )

    def _on_loaded(self, data) -> None:
        if not isinstance(data, dict):
            self._all_convs = []
            self._render_status("Unexpected response")
            return
        self._all_convs = list(data.get("conversations") or [])
        self._stats = data.get("stats") or {}
        self._update_stats()
        self._render_list()

    def _update_stats(self) -> None:
        s = self._stats or {}
        acct = s.get("account_uuid") or ""
        if acct:
            self._stat_account_value.setText(f"{acct[:8]}…")
            self._stat_account_value.setToolTip(acct)
        else:
            self._stat_account_value.setText(" - ")
        n_conv = int(s.get("total_conversations") or 0)
        n_msg = int(s.get("total_messages") or 0)
        self._stat_count_value.setText(
            f"{fmt(n_conv)} conversations · {fmt(n_msg)} messages"
        )
        date_range = s.get("date_range") or {}
        self._stat_range_value.setText(
            f"{_fmt_year_month(date_range.get('earliest'))} → "
            f"{_fmt_year_month(date_range.get('latest'))}"
        )

    def _filtered_convs(self) -> list[dict]:
        key, value = self._chip_value
        if key == "_all":
            return list(self._all_convs)
        if key == "archived":
            return [c for c in self._all_convs if bool(c.get("is_archived")) == bool(value)]
        if key == "_dnr":
            return [c for c in self._all_convs if c.get("is_do_not_remember")]
        if key == "_temp":
            return [c for c in self._all_convs if c.get("is_temporary_chat")]
        return list(self._all_convs)

    def _render_list(self) -> None:
        self._clear_list()
        convs = self._filtered_convs()
        n = len(convs)
        self.count_label.setText(
            f"{fmt(n)} conversation" + ("" if n == 1 else "s")
        )
        if not convs:
            self._render_status(
                "No conversations match" if (self._search or self._chip_value[0] != "_all")
                else "No AI conversations parsed yet"
            )
            return
        for c in convs:
            row = _ConvRow(c)
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

    def _open_detail(self, conv: dict) -> None:
        conv_uuid = conv.get("conversation_uuid")
        if not conv_uuid or not self.state.case_id:
            return
        self._set_detail_loading()
        self.stack.setCurrentIndex(1)
        api.run_async(
            api.get,
            on_result=self._on_detail_loaded,
            on_error=lambda msg: self._set_detail_error(msg),
            path=(
                f"/analysis/evidence/{self.state.case_id}"
                f"/ai-conversations/{conv_uuid}"
            ),
        )

    def _set_detail_loading(self) -> None:
        self._clear_thread()
        self.detail_title.setText("Loading…")
        self.detail_dates.setText("")
        self.detail_account.setText("")
        self._clear_detail_flags()
        self.detail_ci_frame.setVisible(False)

    def _set_detail_error(self, message: str) -> None:
        self._clear_thread()
        self.detail_title.setText("Failed to load conversation")
        self.detail_dates.setText(message)

    def _on_detail_loaded(self, data) -> None:
        if not isinstance(data, dict):
            self._set_detail_error("Unexpected response")
            return
        meta = data.get("meta") or {}
        ci = data.get("custom_instructions") or {}
        messages = list(data.get("messages") or [])

        self.detail_title.setText(meta.get("title") or "(untitled)")
        date_parts = []
        if meta.get("creation_date"):
            date_parts.append(
                f"created {_fmt_message_dt(meta['creation_date'])}"
            )
        if meta.get("modification_date"):
            date_parts.append(
                f"last activity {_fmt_message_dt(meta['modification_date'])}"
            )
        if meta.get("default_model"):
            date_parts.append(f"default model {meta['default_model']}")
        self.detail_dates.setText("  ·  ".join(date_parts))
        acct = meta.get("account_uuid") or ""
        self.detail_account.setText(f"account_uuid: {acct or ' - '}")

        self._clear_detail_flags()
        if meta.get("is_temporary_chat"):
            self._add_detail_flag("Temporary", "#E65100", "#FFF3E0")
        if meta.get("is_do_not_remember"):
            self._add_detail_flag("Don't remember", "#C62828", "#FDECEA")
        if meta.get("is_archived"):
            self._add_detail_flag("Archived", "#555555", "#EAEAE4")
        if meta.get("is_study_mode"):
            self._add_detail_flag("Study mode", "#1565C0", "#E3F2FD")

        ci_user = ci.get("user") or ""
        ci_model = ci.get("model") or ""
        if ci_user or ci_model:
            self.detail_ci_frame.setVisible(True)
            self.detail_ci_user_label.setVisible(bool(ci_user))
            self.detail_ci_user.setVisible(bool(ci_user))
            self.detail_ci_user.setText(ci_user or "")
            self.detail_ci_model_label.setVisible(bool(ci_model))
            self.detail_ci_model.setVisible(bool(ci_model))
            self.detail_ci_model.setText(ci_model or "")
        else:
            self.detail_ci_frame.setVisible(False)

        self._clear_thread()
        for seq, m in enumerate(messages):
            if "seq" not in m or m["seq"] is None:
                m["seq"] = seq
            self.detail_thread_layout.addWidget(self._build_bubble(m))
            self.detail_metadata_layout.addWidget(self._build_metadata_card(m))

    def _add_detail_flag(self, text: str, fg: str, bg: str) -> None:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"QLabel {{ background: {bg}; color: {fg}; font-size: 10px; "
            f"font-weight: 600; padding: 2px 6px; border-radius: 8px; }}"
        )
        idx = self.detail_flags_row.count() - 1
        self.detail_flags_row.insertWidget(max(idx, 0), lbl)

    def _clear_detail_flags(self) -> None:
        while self.detail_flags_row.count() > 1:
            item = self.detail_flags_row.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _clear_thread(self) -> None:
        for layout in (self.detail_thread_layout, self.detail_metadata_layout):
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget() if item else None
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()

    def _build_bubble(self, m: dict) -> QWidget:
        ct = (m.get("content_type") or "text").lower()
        role = (m.get("role") or "").lower()
        if ct == "text":
            if role == "tool":
                return self._build_tool_bubble(m, label="Tool result")
            return self._build_text_bubble(m)
        if ct == "multimodal_text":
            return self._build_multimodal_bubble(m)
        if ct == "code":
            return self._build_code_bubble(m)
        if ct == "thoughts":
            return self._build_thoughts_bubble(m)
        if ct == "reasoning_recap":
            return self._build_reasoning_recap_bubble(m)
        if ct == "execution_output":
            return self._build_tool_bubble(m, label="Code output", monospace=True)
        if ct == "tether_browsing_display":
            return self._build_tool_bubble(m, label="Web browsed")
        if ct == "tether_quote":
            return self._build_tool_bubble(m, label="Quoted from web")
        if ct == "system_error":
            return self._build_error_bubble(m)
        return self._build_unknown_bubble(m)

    @staticmethod
    def _bubble_header(
        m: dict, *, content_type_label: Optional[str] = None,
        accent_badge: Optional[tuple[str, str, str]] = None,
    ) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        role = (m.get("role") or "").lower()
        role_lbl = QLabel(role.capitalize() if role else "?")
        role_lbl.setStyleSheet(
            "font-size: 10px; font-weight: 700; "
            "letter-spacing: 0.4px; background: transparent; color: inherit;"
        )
        header.addWidget(role_lbl)
        if accent_badge:
            text, fg, bg = accent_badge
            chip = QLabel(text)
            chip.setStyleSheet(
                f"QLabel {{ background: {bg}; color: {fg}; font-size: 10px; "
                f"font-weight: 600; padding: 1px 6px; border-radius: 8px; }}"
            )
            header.addWidget(chip)
        if role == "assistant" and m.get("model_slug"):
            model_lbl = QLabel(str(m["model_slug"]))
            model_lbl.setStyleSheet(
                "QLabel { background: #EAEAE4; color: #444444; "
                "font-size: 10px; padding: 1px 6px; border-radius: 6px; }"
            )
            header.addWidget(model_lbl)
        if role == "tool" and m.get("tool_name"):
            tool_lbl = QLabel(str(m["tool_name"]))
            tool_lbl.setStyleSheet(
                "QLabel { background: #E3F2FD; color: #0D47A1; "
                "font-size: 10px; font-weight: 700; padding: 1px 6px; "
                "border-radius: 6px; }"
            )
            header.addWidget(tool_lbl)
        header.addStretch(1)
        if content_type_label:
            ct_lbl = QLabel(content_type_label)
            ct_lbl.setStyleSheet(
                "font-size: 10px; color: #888888; background: transparent;"
            )
            header.addWidget(ct_lbl)
        ts = QLabel(_fmt_message_dt(m.get("create_time")))
        ts.setStyleSheet(
            "font-size: 10px; color: inherit; background: transparent; "
            "opacity: 0.7;"
        )
        header.addWidget(ts)
        return header

    @staticmethod
    def _wrap_aligned(bubble: QFrame, role: str) -> QWidget:
        wrap = QFrame()
        wrap_layout = QHBoxLayout(wrap)
        wrap_layout.setContentsMargins(0, 0, 0, 0)
        wrap_layout.setSpacing(0)
        if role == "user":
            wrap_layout.addStretch(1)
            wrap_layout.addWidget(bubble)
        elif role == "assistant":
            wrap_layout.addWidget(bubble)
            wrap_layout.addStretch(1)
        else:
            wrap_layout.addWidget(bubble, 1)
        return wrap

    def _build_text_bubble(self, m: dict) -> QWidget:
        role = (m.get("role") or "").lower()
        bubble = QFrame()
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.setSpacing(2)
        bl.addLayout(self._bubble_header(m))
        body = QLabel(m.get("content_text") or "")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        body.setMinimumHeight(0)
        if role == "user":
            bubble.setStyleSheet(
                "QFrame { background: #D4EDDF; color: #14432A; "
                "border: 1px solid #B7DCC4; border-radius: 12px; }"
            )
            body.setStyleSheet(
                "font-size: 13px; line-height: 1.4; background: transparent;"
            )
            bubble.setMaximumWidth(560)
        elif role == "assistant":
            bubble.setStyleSheet(
                "QFrame { background: #FFFFFF; color: #1C1C1A; "
                "border: 1px solid #E8E8E2; border-radius: 12px; }"
            )
            body.setStyleSheet(
                "font-size: 13px; line-height: 1.4; background: transparent;"
            )
            bubble.setMaximumWidth(620)
        else:
            bubble.setStyleSheet(
                "QFrame { background: #F6F6F3; color: #555555; "
                "border: 1px dashed #C8C8C0; border-radius: 8px; }"
            )
            body.setStyleSheet(
                "font-size: 12px; font-style: italic; background: transparent;"
            )
        bl.addWidget(body)
        return self._wrap_aligned(bubble, role)

    def _build_tool_bubble(
        self, m: dict, *, label: str, monospace: bool = False
    ) -> QWidget:
        bubble = QFrame()
        bubble.setStyleSheet(
            "QFrame { background: #E3F2FD; color: #0D47A1; "
            "border: 1px solid #B6D4F0; border-radius: 8px; }"
        )
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.setSpacing(4)
        bl.addLayout(self._bubble_header(
            m, accent_badge=(label, "#0D47A1", "#FFFFFF"),
        ))
        body = QLabel(m.get("content_text") or "")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if monospace:
            body.setStyleSheet(
                "font-family: 'JetBrains Mono','Consolas',monospace; "
                "font-size: 11px; color: #0D47A1; background: transparent;"
            )
        else:
            body.setStyleSheet(
                "font-size: 12px; color: #0D47A1; background: transparent;"
            )
        body.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        body.setMinimumHeight(0)
        bl.addWidget(body)
        return self._wrap_aligned(bubble, "tool")

    def _build_code_bubble(self, m: dict) -> QWidget:
        role = (m.get("role") or "assistant").lower()
        lang = m.get("code_language") or "code"
        bubble = QFrame()
        bubble.setStyleSheet(
            "QFrame { background: #1C1C1A; color: #E8E8E2; "
            "border: 1px solid #2A2A28; border-radius: 8px; }"
        )
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.setSpacing(4)
        bl.addLayout(self._bubble_header(
            m, accent_badge=(lang, "#1C1C1A", "#F5C518"),
        ))
        body = QLabel(m.get("content_text") or "")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setStyleSheet(
            "font-family: 'JetBrains Mono','Consolas',monospace; "
            "font-size: 11px; color: #E8E8E2; background: transparent;"
        )
        body.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        body.setMinimumHeight(0)
        bl.addWidget(body)
        bubble.setMaximumWidth(640)
        return self._wrap_aligned(bubble, role)

    def _build_thoughts_bubble(self, m: dict) -> QWidget:
        bubble = QFrame()
        bubble.setStyleSheet(
            "QFrame { background: #F3E5F5; color: #4A148C; "
            "border: 1px solid #D1C4E9; border-radius: 8px; }"
        )
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.setSpacing(4)
        bl.addLayout(self._bubble_header(
            m, accent_badge=("Reasoning", "#4A148C", "#E1BEE7"),
        ))
        body = QLabel(m.get("content_text") or "")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setStyleSheet(
            "font-size: 12px; font-style: italic; color: #4A148C; "
            "background: transparent;"
        )
        body.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        body.setMinimumHeight(0)
        bl.addWidget(body)
        bubble.setMaximumWidth(620)
        return self._wrap_aligned(bubble, "assistant")

    def _build_reasoning_recap_bubble(self, m: dict) -> QWidget:
        bubble = QFrame()
        bubble.setStyleSheet(
            "QFrame { background: #FFFFFF; color: #1C1C1A; "
            "border: 1px solid #D1C4E9; border-radius: 12px; }"
        )
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.setSpacing(4)
        bl.addLayout(self._bubble_header(
            m, accent_badge=("Reasoning summary", "#4A148C", "#F3E5F5"),
        ))
        body = QLabel(m.get("content_text") or "")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setStyleSheet(
            "font-size: 13px; line-height: 1.4; background: transparent;"
        )
        body.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        body.setMinimumHeight(0)
        bl.addWidget(body)
        bubble.setMaximumWidth(620)
        return self._wrap_aligned(bubble, "assistant")

    def _build_multimodal_bubble(self, m: dict) -> QWidget:
        role = (m.get("role") or "user").lower()
        bubble = QFrame()
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.setSpacing(6)
        bl.addLayout(self._bubble_header(m, content_type_label="multimodal"))

        text_part = m.get("content_text") or ""
        if text_part.strip():
            body = QLabel(text_part)
            body.setWordWrap(True)
            body.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            body.setStyleSheet(
                "font-size: 13px; line-height: 1.4; background: transparent;"
            )
            body.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
            )
            body.setMinimumHeight(0)
            bl.addWidget(body)

        for asset in (m.get("image_assets") or []):
            bl.addWidget(self._build_image_card(asset))

        if role == "user":
            bubble.setStyleSheet(
                "QFrame { background: #D4EDDF; color: #14432A; "
                "border: 1px solid #B7DCC4; border-radius: 12px; }"
            )
            bubble.setMaximumWidth(580)
        else:
            bubble.setStyleSheet(
                "QFrame { background: #FFFFFF; color: #1C1C1A; "
                "border: 1px solid #E8E8E2; border-radius: 12px; }"
            )
            bubble.setMaximumWidth(620)
        return self._wrap_aligned(bubble, role)

    @staticmethod
    def _build_image_card(asset: dict) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #EAEAE4; border: 1px solid #D8D8D2; "
            "border-radius: 8px; }"
        )
        width = asset.get("width")
        height = asset.get("height")
        target_w, target_h = 200, 140
        if isinstance(width, (int, float)) and isinstance(height, (int, float)) \
                and width > 0 and height > 0:
            ratio = float(width) / float(height)
            if ratio >= 1:
                target_w = 240
                target_h = max(120, int(target_w / ratio))
            else:
                target_h = 240
                target_w = max(120, int(target_h * ratio))
            target_w = min(target_w, 240)
            target_h = min(target_h, 240)
        card.setFixedSize(target_w, target_h)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)

        ic = QLabel()
        ic.setPixmap(icons.pixmap("image", size=28, color="#7A7A72"))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(ic, 1)

        if isinstance(width, (int, float)) and isinstance(height, (int, float)):
            dims = QLabel(f"{int(width)} × {int(height)}")
            dims.setStyleSheet(
                "font-size: 11px; color: #444444; "
                "background: transparent; border: none;"
            )
            dims.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(dims)

        size_b = asset.get("size_bytes")
        if size_b:
            sz = QLabel(fmt_bytes(int(size_b)))
            sz.setStyleSheet(
                "font-size: 10px; color: #666666; "
                "background: transparent; border: none;"
            )
            sz.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(sz)

        ap = asset.get("asset_pointer") or ""
        if ap:
            trunc = ap if len(ap) <= 16 else ap[:16] + "…"
            ap_lbl = QLabel(trunc)
            ap_lbl.setStyleSheet(
                "font-family: 'JetBrains Mono','Consolas',monospace; "
                "font-size: 9px; color: #888888; "
                "background: transparent; border: none;"
            )
            ap_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ap_lbl.setToolTip(ap)
            layout.addWidget(ap_lbl)

        note = QLabel("Server-side only")
        note.setStyleSheet(
            "font-size: 9px; color: #888888; font-style: italic; "
            "background: transparent; border: none;"
        )
        note.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom
        )
        layout.addWidget(note)
        return card

    def _build_error_bubble(self, m: dict) -> QWidget:
        bubble = QFrame()
        bubble.setStyleSheet(
            "QFrame { background: #FDECEA; color: #C62828; "
            "border: 1px solid #F5B7B1; border-radius: 8px; }"
        )
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.setSpacing(4)
        bl.addLayout(self._bubble_header(
            m, accent_badge=("Error", "#FFFFFF", "#C62828"),
        ))
        body = QLabel(m.get("content_text") or "(no detail)")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setStyleSheet(
            "font-size: 12px; color: #C62828; background: transparent;"
        )
        body.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        body.setMinimumHeight(0)
        bl.addWidget(body)
        return self._wrap_aligned(bubble, "tool")

    def _build_unknown_bubble(self, m: dict) -> QWidget:
        ct = m.get("content_type") or "unknown"
        bubble = QFrame()
        bubble.setStyleSheet(
            "QFrame { background: #FFF8E1; color: #6D4C00; "
            "border: 1px solid #FBC02D; border-radius: 8px; }"
        )
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.setSpacing(4)
        head_label = QLabel(f"Unrecognized content type: {ct}")
        head_label.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #6D4C00; "
            "background: transparent;"
        )
        bl.addWidget(head_label)
        bl.addLayout(self._bubble_header(m))
        body = QLabel(m.get("content_text") or "")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setStyleSheet(
            "font-family: 'JetBrains Mono','Consolas',monospace; "
            "font-size: 11px; color: #6D4C00; background: transparent;"
        )
        body.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        body.setMinimumHeight(0)
        bl.addWidget(body)
        return self._wrap_aligned(bubble, "tool")

    def _build_metadata_card(self, m: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("roundCard")
        apply_card_shadow(card)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(10, 8, 10, 8)
        cl.setSpacing(6)

        seq = m.get("seq")
        role = m.get("role") or "?"
        ct = m.get("content_type") or "text"
        ts = _fmt_message_dt(m.get("create_time"))

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        toggle = QPushButton(
            f"  Message #{seq} · role={role} · type={ct}"
        )
        toggle.setObjectName("btnGhost")
        toggle.setCheckable(True)
        toggle.setIcon(icons.qicon("chevron_right", size=12, color="#62625F"))
        toggle.setIconSize(icons.icon_size(12))
        toggle.setStyleSheet(
            "QPushButton { text-align: left; font-size: 12px; "
            "font-weight: 600; color: #1C1C1A; padding: 4px; }"
            "QPushButton:hover { color: #14432A; }"
        )
        toggle.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        header_row.addWidget(toggle, 1)

        ts_lbl = QLabel(ts)
        ts_lbl.setStyleSheet(
            "font-size: 11px; color: #888888; background: transparent;"
        )
        header_row.addWidget(ts_lbl)

        copy_btn = QPushButton("Copy JSON")
        copy_btn.setObjectName("btnSm")
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setStyleSheet(
            "QPushButton { background: #EAEAE4; color: #62625F; "
            "padding: 4px 10px; font-size: 11px; border-radius: 4px; }"
        )
        header_row.addWidget(copy_btn)
        cl.addLayout(header_row)

        raw_node = m.get("raw_node")
        if raw_node is None:
            pretty = "(no raw_node - older parser run)"
        else:
            try:
                pretty = json.dumps(raw_node, ensure_ascii=False, indent=2)
            except (TypeError, ValueError) as exc:
                pretty = f"(JSON serialization failed: {exc})"

        body = QLabel(pretty)
        body.setStyleSheet(
            "font-family: 'JetBrains Mono','Consolas',monospace; "
            "font-size: 11px; color: #1C1C1A; "
            "background: #FAFAF7; padding: 8px; border: 1px solid #E8E8E2;"
        )
        body.setWordWrap(True)
        body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        body.setVisible(False)
        cl.addWidget(body)

        def _toggle(checked: bool) -> None:
            body.setVisible(checked)
            toggle.setIcon(icons.qicon(
                "chevron_down" if checked else "chevron_right",
                size=12, color="#62625F",
            ))

        toggle.toggled.connect(_toggle)
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(pretty))
        return card

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
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


_TABLE_LABELS = {
    "genp": "Passwords",
    "inet": "Internet",
    "cert": "Certificates",
    "keys": "Keys",
}

_THIS_DEVICE_ONLY = {9, 10, 11}


_CHIPS: list[tuple[str, Optional[str]]] = [
    ("All", None),
    ("Passwords", "genp"),
    ("Internet", "inet"),
    ("Certificates", "cert"),
    ("Keys", "keys"),
]


class _ItemRow(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, item: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._item = item
        self.setObjectName("caseCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        is_tdo = bool(item.get("is_this_device_only"))

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(12)

        table = QLabel(_TABLE_LABELS.get(item.get("table_name") or "", "?"))
        table.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {GREEN_700}; "
            f"background: transparent;"
        )
        table.setFixedWidth(96)
        table.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
        )
        row.addWidget(table)

        mid = QVBoxLayout()
        mid.setSpacing(2)
        cls_text = item.get("protection_class_name") or "?"
        if is_tdo:
            cls_text = f"{cls_text} · ThisDeviceOnly"
        cls = QLabel(cls_text)
        cls_color = "#98988F" if is_tdo else "#1C1C1A"
        cls.setStyleSheet(
            f"font-size: 12px; color: {cls_color}; background: transparent;"
        )
        cls.setWordWrap(True)
        cls.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        cls.setMinimumHeight(0)
        mid.addWidget(cls)
        row.addLayout(mid, 1)

        uuid_full = item.get("item_uuid") or ""
        uuid_short = uuid_full[:8] + "…" + uuid_full[-4:] if len(uuid_full) > 14 else uuid_full
        uid = QLabel(uuid_short)
        uid.setObjectName("monoSm")
        uid.setStyleSheet(
            "font-family: 'JetBrains Mono','Consolas',monospace; font-size: 11px; "
            "color: #62625F; background: transparent;"
        )
        uid.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        uid.setFixedWidth(140)
        uid.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
        )
        row.addWidget(uid)

        if is_tdo:
            self.setStyleSheet("QFrame#caseCard { background: #FAFAF7; }")
        apply_card_shadow(self)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._item)
        super().mousePressEvent(e)


class KeychainPage(QWidget):
    PAGE_SIZE = 100

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._meta: dict = {}
        self._stats: dict = {}
        self._all_items: list[dict] = []
        self._filtered: list[dict] = []
        self._shown_count: int = 0
        self._table_filter: Optional[str] = None

        self.stack = QStackedWidget(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.stack)

        self.stack.addWidget(self._build_browser_view())
        self.stack.addWidget(self._build_detail_view())

        state.case_changed.connect(lambda _: self.refresh())

    def on_show(self) -> None:
        self.refresh()

    def _build_browser_view(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)

        self.outer_scroll = QScrollArea()
        self.outer_scroll.setWidgetResizable(True)
        self.outer_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.outer_scroll.setObjectName("contentArea")
        self.outer_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        enable_touch_scroll(self.outer_scroll)

        host = QWidget()
        col = QVBoxLayout(host)
        col.setContentsMargins(8, 8, 8, 8)
        col.setSpacing(8)

        title_row = QHBoxLayout()
        title = QLabel("Keychain")
        title.setStyleSheet(
            "font-size: 22px; font-weight: 800; background: transparent;"
        )
        title_row.addWidget(title)
        self.count_label = QLabel("0 items indexed")
        self.count_label.setObjectName("mutedText")
        self.count_label.setStyleSheet(
            "background: transparent; padding-left: 8px;"
        )
        title_row.addWidget(self.count_label)
        title_row.addStretch(1)
        col.addLayout(title_row)

        self.info_banner = QFrame()
        self.info_banner.setStyleSheet(
            "QFrame { background: #FFF8E1; border: 1px solid #FBC02D; }"
        )
        ib = QVBoxLayout(self.info_banner)
        ib.setContentsMargins(12, 10, 12, 10)
        ib.setSpacing(2)
        ib_title = QLabel("Plaintext extraction unavailable for this iOS version")
        ib_title.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: #6D4C00; "
            "background: transparent;"
        )
        ib.addWidget(ib_title)
        self.info_text = QLabel("")
        self.info_text.setStyleSheet(
            "font-size: 11px; color: #6D4C00; background: transparent;"
        )
        self.info_text.setWordWrap(True)
        ib.addWidget(self.info_text)
        col.addWidget(self.info_banner)

        stats_frame = QFrame()
        stats_frame.setObjectName("roundCard")
        apply_card_shadow(stats_frame)
        sf = QVBoxLayout(stats_frame)
        sf.setContentsMargins(14, 12, 14, 12)
        sf.setSpacing(6)
        sf_title = QLabel("By table")
        sf_title.setStyleSheet(
            f"color: {GREEN_700}; font-size: 12px; font-weight: 700; "
            f"letter-spacing: 0.5px; background: transparent;"
        )
        sf.addWidget(sf_title)
        self.stats_grid = QGridLayout()
        self.stats_grid.setHorizontalSpacing(16)
        self.stats_grid.setVerticalSpacing(4)
        sf.addLayout(self.stats_grid)
        col.addWidget(stats_frame)

        cls_frame = QFrame()
        cls_frame.setObjectName("roundCard")
        apply_card_shadow(cls_frame)
        cf = QVBoxLayout(cls_frame)
        cf.setContentsMargins(14, 12, 14, 12)
        cf.setSpacing(6)
        cf_title = QLabel("Protection-class distribution")
        cf_title.setStyleSheet(
            f"color: {GREEN_700}; font-size: 12px; font-weight: 700; "
            f"letter-spacing: 0.5px; background: transparent;"
        )
        cf.addWidget(cf_title)
        self.class_bar_wrap = QVBoxLayout()
        self.class_bar_wrap.setSpacing(3)
        cf.addLayout(self.class_bar_wrap)
        col.addWidget(cls_frame)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)
        for label, value in _CHIPS:
            btn = QPushButton(label)
            btn.setObjectName("chipFilter")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if value is None:
                btn.setChecked(True)
            btn.clicked.connect(lambda _checked, v=value: self._set_table_filter(v))
            self._chip_group.addButton(btn)
            chips.addWidget(btn)
        chips.addStretch(1)
        col.addLayout(chips)

        self.list_layout = QVBoxLayout()
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch(1)
        col.addLayout(self.list_layout, 1)

        self.outer_scroll.setWidget(host)
        outer.addWidget(self.outer_scroll)

        def _sync_host_width() -> None:
            host.setMaximumWidth(self.outer_scroll.viewport().width())

        original_resize = self.outer_scroll.resizeEvent

        def _patched_resize(event):
            original_resize(event)
            _sync_host_width()

        self.outer_scroll.resizeEvent = _patched_resize
        _sync_host_width()

        self.outer_scroll.verticalScrollBar().valueChanged.connect(
            self._on_scrolled
        )

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
        self.detail_uuid = QLabel("")
        self.detail_uuid.setObjectName("monoSm")
        self.detail_uuid.setWordWrap(True)
        self.detail_uuid.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        hl.addWidget(self.detail_uuid)
        col.addWidget(header)

        meta_frame = QFrame()
        meta_frame.setObjectName("roundCard")
        apply_card_shadow(meta_frame)
        mf = QVBoxLayout(meta_frame)
        mf.setContentsMargins(14, 12, 14, 12)
        mf.setSpacing(4)
        meta_title = QLabel("Protection")
        meta_title.setStyleSheet(
            f"color: {GREEN_700}; font-size: 12px; font-weight: 700; "
            f"letter-spacing: 0.5px; background: transparent;"
        )
        mf.addWidget(meta_title)
        self.detail_class = QLabel("")
        self.detail_class.setObjectName("monoSm")
        self.detail_class.setWordWrap(True)
        mf.addWidget(self.detail_class)
        self.detail_size = QLabel("")
        self.detail_size.setObjectName("monoSm")
        mf.addWidget(self.detail_size)
        self.detail_decrypted = QLabel("")
        self.detail_decrypted.setObjectName("monoSm")
        mf.addWidget(self.detail_decrypted)
        col.addWidget(meta_frame)

        wkey_frame = QFrame()
        wkey_frame.setObjectName("roundCard")
        apply_card_shadow(wkey_frame)
        wf = QVBoxLayout(wkey_frame)
        wf.setContentsMargins(14, 12, 14, 12)
        wf.setSpacing(4)
        wf_title = QLabel("Wrapped key (40 bytes, hex)")
        wf_title.setStyleSheet(
            f"color: {GREEN_700}; font-size: 12px; font-weight: 700; "
            f"letter-spacing: 0.5px; background: transparent;"
        )
        wf.addWidget(wf_title)
        self.detail_wkey = QLabel("")
        self.detail_wkey.setStyleSheet(
            "font-family: 'JetBrains Mono','Consolas',monospace; font-size: 11px; "
            "background: transparent;"
        )
        self.detail_wkey.setWordWrap(True)
        self.detail_wkey.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        wf.addWidget(self.detail_wkey)
        col.addWidget(wkey_frame)

        col.addStretch(1)

        self.detail_scroll.setWidget(inner)
        outer.addWidget(self.detail_scroll)
        return page

    def refresh(self) -> None:
        if not self.state.case_id:
            return
        self.count_label.setText("Loading…")
        params = {"limit": 5000}
        api.run_async(
            api.get,
            on_result=self._on_loaded,
            on_error=lambda msg: self._render_status(f"Failed to load: {msg}"),
            path=f"/analysis/evidence/{self.state.case_id}/keychain",
            params=params,
        )

    def _on_loaded(self, data) -> None:
        if not isinstance(data, dict):
            self._render_status("Unexpected response")
            return
        self._meta = data.get("meta") or {}
        self._stats = data.get("stats") or {}
        self._all_items = list(data.get("items") or [])
        self._render_overview()
        self._reapply_filter()

    def _render_overview(self) -> None:
        total = int(self._meta.get("total_items") or 0)
        self.count_label.setText(f"{fmt(total)} items indexed")

        tdo = int(self._stats.get("this_device_only_count") or 0)
        ios_v = self._meta.get("ios_version") or "unknown"
        self.info_text.setText(
            f"Cryptographic body extraction not available for iOS {ios_v} - "
            f"protection-class structure and persistent identifiers are "
            f"indexed instead. {fmt(tdo)} items use ThisDeviceOnly "
            f"protection (forensically unrecoverable from any backup)."
        )

        while self.stats_grid.count():
            item = self.stats_grid.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        by_table = self._stats.get("by_table") or {}
        for col_idx, key in enumerate(("genp", "inet", "cert", "keys")):
            cell = QVBoxLayout()
            num = QLabel(fmt(int(by_table.get(key) or 0)))
            num.setStyleSheet(
                "font-size: 18px; font-weight: 800; background: transparent;"
            )
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label = QLabel(_TABLE_LABELS.get(key, key))
            label.setObjectName("subtle")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            wrap = QWidget()
            wl = QVBoxLayout(wrap)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setSpacing(0)
            wl.addWidget(num)
            wl.addWidget(label)
            self.stats_grid.addWidget(wrap, 0, col_idx)

        while self.class_bar_wrap.count():
            item = self.class_bar_wrap.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        by_class = self._stats.get("by_class") or {}
        max_count = max((int(v) for v in by_class.values()), default=1) or 1
        for cls_str in sorted(by_class.keys(), key=lambda x: int(x)):
            cls = int(cls_str)
            count = int(by_class[cls_str])
            if count == 0:
                continue
            row = QHBoxLayout()
            lbl = QLabel(f"Class {cls}")
            lbl.setObjectName("monoSm")
            lbl.setFixedWidth(64)
            row.addWidget(lbl)
            bar = QFrame()
            width_pct = int(round(count / max_count * 100))
            color = "#C8C8C0" if cls in _THIS_DEVICE_ONLY else GREEN_700
            bar.setStyleSheet(
                f"QFrame {{ background: {color}; min-height: 10px; }}"
            )
            bar.setMinimumWidth(max(2, int(width_pct * 3)))
            bar.setFixedHeight(10)
            row.addWidget(bar)
            cnt_lbl = QLabel(fmt(count))
            cnt_lbl.setObjectName("monoSm")
            cnt_lbl.setFixedWidth(56)
            cnt_lbl.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            row.addWidget(cnt_lbl)
            row.addStretch(1)
            wrap = QWidget()
            wrap.setLayout(row)
            self.class_bar_wrap.addWidget(wrap)

    def _set_table_filter(self, value: Optional[str]) -> None:
        self._table_filter = value
        self._reapply_filter()

    def _reapply_filter(self) -> None:
        if self._table_filter is None:
            self._filtered = list(self._all_items)
        else:
            self._filtered = [
                i for i in self._all_items
                if (i.get("table_name") or "") == self._table_filter
            ]
        self._shown_count = min(self.PAGE_SIZE, len(self._filtered))
        self._render_list()

    def _render_list(self) -> None:
        self._clear_list()
        if not self._filtered:
            self._render_status("No items match this filter")
            return
        for item in self._filtered[: self._shown_count]:
            row = _ItemRow(item)
            row.clicked.connect(self._open_detail)
            self.list_layout.insertWidget(self.list_layout.count() - 1, row)

    def _on_scrolled(self, value: int) -> None:
        sb = self.outer_scroll.verticalScrollBar()
        max_val = sb.maximum()
        if max_val <= 0:
            return
        if value < max_val - 200:
            return
        if self._shown_count >= len(self._filtered):
            return
        prev_shown = self._shown_count
        new_shown = min(
            self._shown_count + self.PAGE_SIZE, len(self._filtered)
        )
        if new_shown == prev_shown:
            return
        for item in self._filtered[prev_shown:new_shown]:
            row = _ItemRow(item)
            row.clicked.connect(self._open_detail)
            self.list_layout.insertWidget(self.list_layout.count() - 1, row)
        self._shown_count = new_shown

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

    def _open_detail(self, item: dict) -> None:
        table = _TABLE_LABELS.get(item.get("table_name") or "", item.get("table_name") or "?")
        self.detail_title.setText(f"{table} item")
        self.detail_uuid.setText(f"UUID: {item.get('item_uuid') or ' - '}")

        cls = item.get("protection_class")
        cls_name = item.get("protection_class_name") or "?"
        tdo = " · ThisDeviceOnly (unrecoverable)" if item.get("is_this_device_only") else ""
        self.detail_class.setText(
            f"Class: {cls if cls is not None else '?'} - {cls_name}{tdo}"
        )
        self.detail_size.setText(
            f"v_Data size: {item.get('v_data_size')} bytes"
        )
        self.detail_decrypted.setText(
            "Decrypted: yes" if item.get("decrypted") else "Decrypted: pending v2"
        )

        wkey = item.get("wrapped_key_hex") or ""
        grouped = " ".join(wkey[i:i + 8] for i in range(0, len(wkey), 8))
        self.detail_wkey.setText(grouped or " - ")

        self.stack.setCurrentIndex(1)

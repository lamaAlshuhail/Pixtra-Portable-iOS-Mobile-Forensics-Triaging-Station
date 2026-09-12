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
from ..format import fmt, fmt_time
from ..state import AppState
from ..theme import GREEN_700, apply_card_shadow
from ..touch import enable_touch_scroll


_CHIPS: list[tuple[str, Optional[str]]] = [
    ("All", None),
    ("Boarding", "boarding_pass"),
    ("Tickets", "event_ticket"),
    ("Coupons", "coupon"),
    ("Store Cards", "store_card"),
    ("Generic", "generic"),
]

_TYPE_ICONS = {
    "boarding_pass": "plane",
    "event_ticket": "ticket",
    "coupon": "gift",
    "store_card": "credit_card",
    "generic": "file_text",
}

_TYPE_LABELS = {
    "boarding_pass": "Boarding pass",
    "event_ticket": "Event ticket",
    "coupon": "Coupon",
    "store_card": "Store card",
    "generic": "Generic pass",
}


def _normalize_color(raw: str) -> Optional[str]:
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("rgb(") and s.endswith(")"):
        return s
    if s.startswith("#") and len(s) in (4, 7):
        return s
    return None


class _PassRow(QFrame):

    clicked = pyqtSignal(dict)

    def __init__(self, p: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pass = p
        self.setObjectName("caseCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        band = QFrame()
        band.setFixedWidth(4)
        fg = _normalize_color(p.get("foreground_color") or "") or GREEN_700
        band.setStyleSheet(f"background: {fg};")
        row.addWidget(band)

        body = QHBoxLayout()
        body.setContentsMargins(14, 10, 14, 10)
        body.setSpacing(12)

        ptype = (p.get("pass_type") or "generic").lower()
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(32, 32)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setPixmap(
            icons.pixmap(_TYPE_ICONS.get(ptype, "file_text"), size=20, color=GREEN_700)
        )
        icon_lbl.setStyleSheet("background: transparent;")
        body.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        org = QLabel(p.get("organization_name") or "(no organization)")
        org.setStyleSheet(
            "font-size: 13px; font-weight: 600; background: transparent;"
        )
        org.setWordWrap(True)
        org.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        org.setMinimumHeight(0)
        text_col.addWidget(org)

        desc = p.get("description") or _TYPE_LABELS.get(ptype, "Pass")
        sub = QLabel(desc)
        sub.setObjectName("subtle")
        sub.setWordWrap(True)
        sub.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        sub.setMinimumHeight(0)
        text_col.addWidget(sub)
        body.addLayout(text_col, 1)

        rel = p.get("relevant_date")
        if rel:
            ts = QLabel(fmt_time(rel) or str(rel))
            ts.setObjectName("monoSm")
            ts.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            ts.setFixedWidth(110)
            ts.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
            )
            body.addWidget(ts)

        row.addLayout(body, 1)

        apply_card_shadow(self)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._pass)
        super().mousePressEvent(e)


class WalletPage(QWidget):
    navigate_requested = pyqtSignal(str)

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._all_passes: list[dict] = []
        self._filtered_passes: list[dict] = []
        self._pass_type: Optional[str] = None

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
        col = QVBoxLayout(page)
        col.setContentsMargins(8, 8, 8, 8)
        col.setSpacing(8)

        title_row = QHBoxLayout()
        title = QLabel("Wallet & Passes")
        title.setStyleSheet(
            "font-size: 22px; font-weight: 800; background: transparent;"
        )
        title_row.addWidget(title)
        self.count_label = QLabel("0 passes")
        self.count_label.setObjectName("mutedText")
        self.count_label.setStyleSheet(
            "background: transparent; padding-left: 8px;"
        )
        title_row.addWidget(self.count_label)
        title_row.addStretch(1)
        col.addLayout(title_row)

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
            btn.clicked.connect(lambda _checked, v=value: self._set_pass_type(v))
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
        outer.setSpacing(0)

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

        self.detail_header = QFrame()
        self.detail_header.setObjectName("roundCard")
        apply_card_shadow(self.detail_header)
        hl = QVBoxLayout(self.detail_header)
        hl.setContentsMargins(14, 12, 14, 12)
        hl.setSpacing(4)
        self.detail_org = QLabel("")
        self.detail_org.setStyleSheet(
            "font-size: 16px; font-weight: 700; background: transparent;"
        )
        self.detail_org.setWordWrap(True)
        hl.addWidget(self.detail_org)
        self.detail_type = QLabel("")
        self.detail_type.setObjectName("mutedText")
        hl.addWidget(self.detail_type)
        self.detail_dates = QLabel("")
        self.detail_dates.setObjectName("subtle")
        self.detail_dates.setWordWrap(True)
        hl.addWidget(self.detail_dates)
        col.addWidget(self.detail_header)

        self.detail_fields_frame = QFrame()
        self.detail_fields_frame.setObjectName("roundCard")
        apply_card_shadow(self.detail_fields_frame)
        ff = QVBoxLayout(self.detail_fields_frame)
        ff.setContentsMargins(14, 12, 14, 12)
        ff.setSpacing(6)
        fields_title = QLabel("Fields")
        fields_title.setStyleSheet(
            f"color: {GREEN_700}; font-size: 12px; font-weight: 700; "
            f"letter-spacing: 0.5px; background: transparent;"
        )
        ff.addWidget(fields_title)
        self.detail_fields_grid = QGridLayout()
        self.detail_fields_grid.setHorizontalSpacing(12)
        self.detail_fields_grid.setVerticalSpacing(4)
        ff.addLayout(self.detail_fields_grid)
        col.addWidget(self.detail_fields_frame)

        self.detail_barcode_frame = QFrame()
        self.detail_barcode_frame.setObjectName("roundCard")
        apply_card_shadow(self.detail_barcode_frame)
        bf = QVBoxLayout(self.detail_barcode_frame)
        bf.setContentsMargins(14, 12, 14, 12)
        bf.setSpacing(4)
        self.detail_barcode_title = QLabel("Barcode")
        self.detail_barcode_title.setStyleSheet(
            f"color: {GREEN_700}; font-size: 12px; font-weight: 700; "
            f"letter-spacing: 0.5px; background: transparent;"
        )
        bf.addWidget(self.detail_barcode_title)
        self.detail_barcode_msg = QLabel("")
        self.detail_barcode_msg.setObjectName("monoSm")
        self.detail_barcode_msg.setWordWrap(True)
        self.detail_barcode_msg.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        bf.addWidget(self.detail_barcode_msg)
        col.addWidget(self.detail_barcode_frame)

        self.detail_meta_frame = QFrame()
        self.detail_meta_frame.setObjectName("roundCard")
        apply_card_shadow(self.detail_meta_frame)
        mf = QVBoxLayout(self.detail_meta_frame)
        mf.setContentsMargins(14, 12, 14, 12)
        mf.setSpacing(4)
        meta_title = QLabel("Forensic reference")
        meta_title.setStyleSheet(
            f"color: {GREEN_700}; font-size: 12px; font-weight: 700; "
            f"letter-spacing: 0.5px; background: transparent;"
        )
        mf.addWidget(meta_title)
        self.detail_serial = QLabel("")
        self.detail_serial.setObjectName("monoSm")
        self.detail_serial.setWordWrap(True)
        self.detail_serial.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        mf.addWidget(self.detail_serial)
        self.detail_pkpass = QLabel("")
        self.detail_pkpass.setObjectName("monoSm")
        self.detail_pkpass.setWordWrap(True)
        self.detail_pkpass.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        mf.addWidget(self.detail_pkpass)
        col.addWidget(self.detail_meta_frame)

        col.addStretch(1)

        self.detail_scroll.setWidget(inner)
        outer.addWidget(self.detail_scroll)
        return page

    def refresh(self) -> None:
        if not self.state.case_id:
            return
        self._all_passes = []
        self._filtered_passes = []
        self._render_status("Loading wallet…")
        api.run_async(
            api.get,
            on_result=self._on_loaded,
            on_error=lambda msg: self._render_status(f"Failed to load: {msg}"),
            path=f"/analysis/evidence/{self.state.case_id}/wallet-passes",
        )

    def _on_loaded(self, data) -> None:
        if isinstance(data, dict):
            self._all_passes = list(data.get("passes") or [])
        else:
            self._all_passes = list(data or [])
        self._reapply_filter()

    def _set_pass_type(self, value: Optional[str]) -> None:
        self._pass_type = value
        self._reapply_filter()

    def _reapply_filter(self) -> None:
        if self._pass_type is None:
            self._filtered_passes = list(self._all_passes)
        else:
            self._filtered_passes = [
                p for p in self._all_passes
                if (p.get("pass_type") or "generic") == self._pass_type
            ]
        self._render_list()

    def _render_list(self) -> None:
        self._clear_list()
        total = len(self._all_passes)
        filt = len(self._filtered_passes)
        if filt == total:
            self.count_label.setText(f"{fmt(total)} passes")
        else:
            self.count_label.setText(f"{fmt(filt)} of {fmt(total)} passes")

        if not self._filtered_passes:
            self._render_status(
                "No passes match" if self._all_passes else "No wallet passes"
            )
            return

        for p in self._filtered_passes:
            row = _PassRow(p)
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

    def _open_detail(self, p: dict) -> None:
        ptype = (p.get("pass_type") or "generic").lower()
        self.detail_org.setText(p.get("organization_name") or "(no organization)")
        type_line = _TYPE_LABELS.get(ptype, "Pass")
        if p.get("description"):
            type_line = f"{type_line} · {p['description']}"
        self.detail_type.setText(type_line)

        dates = []
        if p.get("relevant_date"):
            dates.append(f"Relevant: {fmt_time(p['relevant_date']) or p['relevant_date']}")
        if p.get("expiration_date"):
            dates.append(
                f"Expires: {fmt_time(p['expiration_date']) or p['expiration_date']}"
            )
        self.detail_dates.setText(" · ".join(dates) if dates else "")
        self.detail_dates.setVisible(bool(dates))

        while self.detail_fields_grid.count():
            item = self.detail_fields_grid.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        fields = p.get("fields") or {}
        if fields:
            self.detail_fields_frame.setVisible(True)
            for r, (k, v) in enumerate(fields.items()):
                k_lbl = QLabel(k.replace("_", " ").title())
                k_lbl.setObjectName("formLabel")
                v_lbl = QLabel(str(v))
                v_lbl.setObjectName("monoSm")
                v_lbl.setWordWrap(True)
                v_lbl.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                self.detail_fields_grid.addWidget(k_lbl, r, 0)
                self.detail_fields_grid.addWidget(v_lbl, r, 1)
        else:
            self.detail_fields_frame.setVisible(False)

        bc_fmt = p.get("barcode_format")
        bc_msg = p.get("barcode_message")
        if bc_fmt or bc_msg:
            self.detail_barcode_frame.setVisible(True)
            self.detail_barcode_title.setText(f"Barcode: {bc_fmt or 'unknown'}")
            self.detail_barcode_msg.setText(bc_msg or "(no message)")
        else:
            self.detail_barcode_frame.setVisible(False)

        self.detail_serial.setText(f"Serial: {p.get('serial_number') or ' - '}")
        self.detail_pkpass.setText(f"Path: {p.get('pkpass_dir') or ' - '}")

        self.stack.setCurrentIndex(1)

from __future__ import annotations

import hashlib
from typing import Optional

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPixmap
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
from ..format import fmt, fmt_bytes
from ..state import AppState
from ..theme import GREEN_700, apply_card_shadow
from ..touch import enable_touch_scroll


_AVATAR_COLORS = [
    "#1B5E3B",
    "#1565C0",
    "#6A1B9A",
    "#E65100",
    "#C62828",
    "#2E7D32",
    "#00838F",
    "#AD1457",
    "#F57F17",
    "#37474F",
]


def _avatar_color(bundle_id: str) -> str:
    h = hashlib.md5((bundle_id or "").encode("utf-8")).hexdigest()
    return _AVATAR_COLORS[int(h[:8], 16) % len(_AVATAR_COLORS)]


_avatar_cache: dict[tuple[str, str], QPixmap] = {}


def _avatar_pixmap(letter: str, color_hex: str, size: int = 36) -> QPixmap:
    key = ((letter or "?")[0].upper(), color_hex)
    cached = _avatar_cache.get(key)
    if cached is not None:
        return cached
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color_hex))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, size, size, 8, 8)
    painter.setPen(QColor("#FFFFFF"))
    f = QFont()
    f.setPointSize(max(8, size // 2 - 2))
    f.setBold(True)
    painter.setFont(f)
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, key[0])
    painter.end()
    _avatar_cache[key] = pix
    return pix


class _AppRow(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, app: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._app = app
        self.setObjectName("caseCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        is_known = bool(app.get("is_known"))
        has_data = bool(app.get("has_data"))
        self.setStyleSheet(
            "" if (has_data or not is_known)
            else "QFrame#caseCard { color: #555555; }"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(12)

        primary = app.get("display_name") or app.get("bundle_id") or "?"
        avatar = QLabel()
        avatar.setFixedSize(36, 36)
        avatar.setPixmap(_avatar_pixmap(primary, _avatar_color(app.get("bundle_id") or ""), 36))
        avatar.setStyleSheet("background: transparent;")
        row.addWidget(avatar)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        line1 = QHBoxLayout()
        line1.setSpacing(8)
        primary_lbl = QLabel(primary)
        primary_lbl.setStyleSheet(
            "font-size: 14px; font-weight: 600; background: transparent;"
        )
        primary_lbl.setWordWrap(True)
        primary_lbl.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        primary_lbl.setMinimumHeight(0)
        line1.addWidget(primary_lbl, 1)

        size_b = app.get("sandbox_size")
        size_lbl = QLabel(fmt_bytes(size_b) if size_b else "")
        size_lbl.setObjectName("monoSm")
        size_lbl.setStyleSheet(
            "font-size: 11px; color: #1C1C1A; background: transparent;"
        )
        size_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        size_lbl.setFixedWidth(72)
        size_lbl.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
        )
        line1.addWidget(size_lbl)
        text_col.addLayout(line1)

        line2 = QHBoxLayout()
        line2.setSpacing(8)
        bid_lbl = QLabel(app.get("bundle_id") or "")
        bid_lbl.setStyleSheet(
            "font-family: 'JetBrains Mono','Consolas',monospace; "
            "font-size: 11px; color: #888888; background: transparent;"
        )
        bid_lbl.setWordWrap(True)
        bid_lbl.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        bid_lbl.setMinimumHeight(0)
        line2.addWidget(bid_lbl, 1)

        meta_parts = []
        cat = app.get("category") or ""
        vendor = app.get("vendor") or ""
        if cat:
            meta_parts.append(cat)
        if vendor and vendor != cat:
            meta_parts.append(vendor)
        meta_lbl = QLabel(" · ".join(meta_parts))
        meta_lbl.setStyleSheet(
            "font-size: 11px; color: #888888; background: transparent;"
        )
        meta_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        meta_lbl.setFixedWidth(180)
        meta_lbl.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
        )
        line2.addWidget(meta_lbl)
        text_col.addLayout(line2)

        if has_data:
            line3 = QLabel(f"has data - {fmt_bytes(size_b)} on disk")
            line3.setStyleSheet(
                f"font-size: 11px; color: {GREEN_700}; "
                f"background: transparent;"
            )
            text_col.addWidget(line3)

        row.addLayout(text_col, 1)
        apply_card_shadow(self)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._app)
        super().mousePressEvent(e)


class InstalledAppsPage(QWidget):
    navigate_requested = pyqtSignal(str)

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._apps: list[dict] = []
        self._stats: dict = {}
        self._category: Optional[str] = None
        self._search: str = ""
        self._chip_buttons: list[QPushButton] = []
        self._chips_built: bool = False

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
        frame.setFixedHeight(44)
        col = QVBoxLayout(frame)
        col.setContentsMargins(10, 4, 10, 4)
        col.setSpacing(1)
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
        lbl_value.setWordWrap(False)
        col.addWidget(lbl_value)
        return frame, lbl_value

    def _build_browser_view(self) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(8, 6, 8, 8)
        col.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        title = QLabel("Installed Apps")
        title.setStyleSheet(
            "font-size: 20px; font-weight: 800; background: transparent;"
        )
        top.addWidget(title)
        self.count_label = QLabel("0 apps")
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
        self.search_input.setPlaceholderText("Search bundle id or name…")
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
        self._stat_total_frame, self._stat_total_value = self._build_stat_card(
            "Total apps"
        )
        self._stat_user_frame, self._stat_user_value = self._build_stat_card(
            "User apps"
        )
        self._stat_data_frame, self._stat_data_value = self._build_stat_card(
            "Apps with data on disk"
        )
        stats.addWidget(self._stat_total_frame, 1)
        stats.addWidget(self._stat_user_frame, 1)
        stats.addWidget(self._stat_data_frame, 1)
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
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 12, 14, 12)
        hl.setSpacing(12)
        self.detail_avatar = QLabel()
        self.detail_avatar.setFixedSize(48, 48)
        self.detail_avatar.setStyleSheet("background: transparent;")
        hl.addWidget(self.detail_avatar)
        head_col = QVBoxLayout()
        head_col.setSpacing(3)
        self.detail_name = QLabel("")
        self.detail_name.setStyleSheet(
            "font-size: 18px; font-weight: 700; background: transparent;"
        )
        self.detail_name.setWordWrap(True)
        head_col.addWidget(self.detail_name)
        self.detail_bundle = QLabel("")
        self.detail_bundle.setStyleSheet(
            "font-family: 'JetBrains Mono','Consolas',monospace; font-size: 11px; "
            "color: #888888; background: transparent;"
        )
        self.detail_bundle.setWordWrap(True)
        self.detail_bundle.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        head_col.addWidget(self.detail_bundle)
        self.detail_category = QLabel("")
        self.detail_category.setStyleSheet(
            "font-size: 12px; color: #444444; background: transparent;"
        )
        head_col.addWidget(self.detail_category)
        hl.addLayout(head_col, 1)
        col.addWidget(header)

        evid = QFrame()
        evid.setObjectName("roundCard")
        apply_card_shadow(evid)
        ef = QVBoxLayout(evid)
        ef.setContentsMargins(14, 12, 14, 12)
        ef.setSpacing(6)
        evid_title = QLabel("Forensic evidence")
        evid_title.setStyleSheet(
            f"color: {GREEN_700}; font-size: 12px; font-weight: 700; "
            f"letter-spacing: 0.5px; background: transparent;"
        )
        ef.addWidget(evid_title)

        self.detail_sandbox_path_label = QLabel("Sandbox path")
        self.detail_sandbox_path_label.setObjectName("formLabel")
        ef.addWidget(self.detail_sandbox_path_label)
        self.detail_sandbox_path = QLabel("")
        self.detail_sandbox_path.setStyleSheet(
            "font-family: 'JetBrains Mono','Consolas',monospace; font-size: 11px; "
            "background: transparent;"
        )
        self.detail_sandbox_path.setWordWrap(True)
        self.detail_sandbox_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        ef.addWidget(self.detail_sandbox_path)

        self.detail_bundle_path_label = QLabel("Bundle path")
        self.detail_bundle_path_label.setObjectName("formLabel")
        ef.addWidget(self.detail_bundle_path_label)
        self.detail_bundle_path = QLabel("")
        self.detail_bundle_path.setStyleSheet(
            "font-family: 'JetBrains Mono','Consolas',monospace; font-size: 11px; "
            "background: transparent;"
        )
        self.detail_bundle_path.setWordWrap(True)
        self.detail_bundle_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        ef.addWidget(self.detail_bundle_path)

        self.detail_data_label = QLabel("Sandbox data on device")
        self.detail_data_label.setObjectName("formLabel")
        ef.addWidget(self.detail_data_label)
        self.detail_data_value = QLabel("")
        self.detail_data_value.setObjectName("monoSm")
        ef.addWidget(self.detail_data_value)

        self.detail_scene_label = QLabel("Last scene id")
        self.detail_scene_label.setObjectName("formLabel")
        ef.addWidget(self.detail_scene_label)
        self.detail_scene_value = QLabel("")
        self.detail_scene_value.setStyleSheet(
            "font-family: 'JetBrains Mono','Consolas',monospace; font-size: 11px; "
            "background: transparent;"
        )
        self.detail_scene_value.setWordWrap(True)
        self.detail_scene_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        ef.addWidget(self.detail_scene_value)
        self.detail_scene_caption = QLabel(
            "evidence of last interactive session"
        )
        self.detail_scene_caption.setObjectName("subtle")
        ef.addWidget(self.detail_scene_caption)

        self.detail_scene_count = QLabel("")
        self.detail_scene_count.setObjectName("monoSm")
        ef.addWidget(self.detail_scene_count)
        self.detail_scene_count_caption = QLabel(
            "distinct interactive sessions recorded"
        )
        self.detail_scene_count_caption.setObjectName("subtle")
        ef.addWidget(self.detail_scene_count_caption)
        col.addWidget(evid)

        ident = QFrame()
        ident.setObjectName("roundCard")
        apply_card_shadow(ident)
        idf = QVBoxLayout(ident)
        idf.setContentsMargins(14, 12, 14, 12)
        idf.setSpacing(4)
        ident_title = QLabel("App identification")
        ident_title.setStyleSheet(
            f"color: {GREEN_700}; font-size: 12px; font-weight: 700; "
            f"letter-spacing: 0.5px; background: transparent;"
        )
        idf.addWidget(ident_title)
        self.detail_source = QLabel("")
        self.detail_source.setObjectName("monoSm")
        self.detail_source.setWordWrap(True)
        idf.addWidget(self.detail_source)
        self.detail_ident_category = QLabel("")
        self.detail_ident_category.setObjectName("monoSm")
        idf.addWidget(self.detail_ident_category)
        self.detail_vendor = QLabel("")
        self.detail_vendor.setObjectName("monoSm")
        idf.addWidget(self.detail_vendor)
        self.detail_is_known = QLabel("")
        self.detail_is_known.setObjectName("monoSm")
        idf.addWidget(self.detail_is_known)
        col.addWidget(ident)

        col.addStretch(1)

        self.detail_scroll.setWidget(inner)
        outer.addWidget(self.detail_scroll)
        return page

    def refresh(self) -> None:
        if not self.state.case_id:
            return
        self._render_status("Loading apps…")
        self._fetch()

    def _on_search_changed(self, text: str) -> None:
        self._search = (text or "").strip()
        self._search_debounce.start()

    def _set_category(self, value: Optional[str]) -> None:
        self._category = value
        self._fetch()

    def _fetch(self) -> None:
        if not self.state.case_id:
            return
        params: dict = {}
        if self._search and len(self._search) > 1:
            params["search"] = self._search
        if self._category:
            params["category"] = self._category
        api.run_async(
            api.get,
            on_result=self._on_loaded,
            on_error=lambda msg: self._render_status(f"Failed to load: {msg}"),
            path=f"/analysis/evidence/{self.state.case_id}/installed-apps",
            params=params or None,
        )

    def _on_loaded(self, data) -> None:
        if not isinstance(data, dict):
            self._apps = []
            self._render_status("Unexpected response")
            return
        self._apps = list(data.get("apps") or [])
        self._stats = data.get("stats") or {}
        self._update_stats()
        if not self._chips_built:
            self._rebuild_chips()
            self._chips_built = True
        self._render_list()

    def _update_stats(self) -> None:
        s = self._stats or {}
        total = int(s.get("total") or 0)
        user_apps = int(s.get("user_apps") or 0)
        with_data = int(s.get("with_data_on_disk") or 0)
        total_bytes = int(s.get("total_sandbox_bytes") or 0)

        self.count_label.setText(
            f"{fmt(len(self._apps))} of {fmt(total)} shown"
            if len(self._apps) != total
            else f"{fmt(total)} apps"
        )
        self._stat_total_value.setText(f"{fmt(total)}")
        pct = f" ({int(round(user_apps / total * 100))}%)" if total else ""
        self._stat_user_value.setText(f"{fmt(user_apps)}{pct}")
        if with_data:
            self._stat_data_value.setText(
                f"{fmt(with_data)} · {fmt_bytes(total_bytes)}"
            )
        else:
            self._stat_data_value.setText("0")

    def _rebuild_chips(self) -> None:
        for btn in self._chip_buttons:
            self._chip_group.removeButton(btn)
            btn.setParent(None)
            btn.deleteLater()
        self._chip_buttons = []

        s = self._stats or {}
        fixed = [
            ("All", None, int(s.get("total") or 0)),
            ("User", "user", int(s.get("user_apps") or 0)),
            ("System", "system", int(s.get("system_apps") or 0)),
        ]
        for label, value, n in fixed:
            self._add_chip(label, value, n, default_checked=(value is None))

        by_cat = s.get("by_category") or {}
        for cat_name, n in sorted(by_cat.items(), key=lambda kv: -int(kv[1] or 0)):
            if not cat_name or cat_name in ("System", "Unknown"):
                continue
            self._add_chip(cat_name, cat_name, int(n), default_checked=False)

    def _add_chip(
        self, label: str, value: Optional[str], n: int, default_checked: bool
    ) -> None:
        text = f"{label} · {fmt(n)}" if n else label
        btn = QPushButton(text)
        btn.setObjectName("chipFilter")
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if default_checked:
            btn.setChecked(True)
        btn.clicked.connect(lambda _checked, v=value: self._set_category(v))
        self._chip_group.addButton(btn)
        self.chips_row.insertWidget(self.chips_row.count() - 1, btn)
        self._chip_buttons.append(btn)

    def _render_list(self) -> None:
        self._clear_list()
        if not self._apps:
            self._render_status(
                "No apps match" if self._search or self._category else "No installed apps"
            )
            return
        for app in self._apps:
            row = _AppRow(app)
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

    def _open_detail(self, app: dict) -> None:
        primary = app.get("display_name") or app.get("bundle_id") or "?"
        self.detail_avatar.setPixmap(
            _avatar_pixmap(primary, _avatar_color(app.get("bundle_id") or ""), 48)
        )
        self.detail_name.setText(primary)
        self.detail_bundle.setText(app.get("bundle_id") or "")
        cat_parts = []
        if app.get("category"):
            cat_parts.append(app["category"])
        if app.get("vendor"):
            cat_parts.append(app["vendor"])
        self.detail_category.setText(" · ".join(cat_parts))

        self.detail_sandbox_path.setText(app.get("sandbox_path") or " - ")
        self.detail_bundle_path.setText(app.get("bundle_path") or " - ")

        size_b = app.get("sandbox_size")
        if size_b and size_b > 0:
            self.detail_data_value.setText(f"Yes - {fmt_bytes(size_b)}")
        else:
            self.detail_data_value.setText("Not staged in current acquisition")

        self.detail_scene_value.setText(app.get("last_scene_id") or " - ")
        self.detail_scene_count.setText(
            f"{fmt(int(app.get('scene_count') or 0))} scenes"
        )

        self.detail_source.setText(
            "Display name source: "
            + (
                "Pixtra catalog (curated)" if app.get("is_known")
                else "Bundle ID only - unrecognized"
            )
        )
        self.detail_ident_category.setText(
            f"Category: {app.get('category') or ' - '}"
        )
        self.detail_vendor.setText(f"Vendor: {app.get('vendor') or ' - '}")
        self.detail_is_known.setText(
            f"is_known: {'yes' if app.get('is_known') else 'no'}"
        )

        self.stack.setCurrentIndex(1)

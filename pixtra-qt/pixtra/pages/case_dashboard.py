import time
from datetime import datetime
from typing import Callable, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
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

from .. import api
from ..format import fmt
from ..state import AppState
from ..theme import (
    GREEN_700,
    SPACING_TILE,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TYPE_MD,
    TYPE_XS,
    apply_card_shadow,
)
from ..touch import enable_touch_scroll
from ..widgets.list_row import ListRow
from ..widgets.tile import Tile


_TILE_DEFS: list[tuple[str, list[tuple]]] = [
    (
        "Communications",
        [
            ("whatsapp",  "message_square", "WhatsApp",  lambda c, s, p: s.get("whatsapp", 0),  False),
            ("imessage",  "message_square", "iMessage",  lambda c, s, p: s.get("imessage", 0),  False),
            ("sms",       "mail",           "SMS",       lambda c, s, p: s.get("sms", 0),       False),
            ("calls",     "phone",          "Calls",     lambda c, s, p: c.get("calls", 0),     False),
            ("ai_chats",  "message_circle", "AI Chats",  lambda c, s, p: c.get("ai_conversations", 0), False),
        ],
    ),
    (
        "Personal",
        [
            ("contacts", "book_user",   "Contacts", lambda c, s, p: c.get("contacts", 0), False),
            ("photos",   "image",       "Photos",   lambda c, s, p: p,                    False),
            ("files",    "folder_open", "Files",    lambda c, s, p: "Browse",             False),
            ("calendar", "calendar",    "Calendar", lambda c, s, p: None,                 False),
            ("wallet",   "credit_card", "Wallet",   lambda c, s, p: None,                 False),
        ],
    ),
    (
        "Activity",
        [
            ("web",       "globe",     "Web History",     lambda c, s, p: c.get("web_history", 0),    False),
            ("locations", "map_pin",   "Locations",       lambda c, s, p: c.get("locations", 0),      False),
            ("apps",      "grid_3x3",  "Installed Apps",  lambda c, s, p: c.get("installed_apps", 0), False),
        ],
    ),
    (
        "Security",
        [
            ("keychain", "key",  "Keychain",       lambda c, s, p: c.get("keychain_items", 0), False),
            ("connectivity_pairing", "smartphone", "Connectivity & Pairing",
             lambda c, s, p: None, True),
        ],
    ),
    (
        "Forensic",
        [
            ("timeline", "clock",        "Timeline",          lambda c, s, p: None, False),
            ("graph",    "git_fork",     "Entity Graph",      lambda c, s, p: None, False),
            ("custody",  "shield_check", "Chain of Custody",  lambda c, s, p: None, False),
            ("reports",  "file_output",  "Reports",           lambda c, s, p: None, False),
        ],
    ),
    (
        "Operations",
        [
            ("acquire", "download", "Acquire", lambda c, s, p: None, False),
        ],
    ),
]


class CaseDashboardPage(QWidget):

    navigate_requested = pyqtSignal(str)
    sim_scan_requested = pyqtSignal(object)

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._stat_value_labels: dict[str, QLabel] = {}
        self._tile_resolvers: dict[Tile, Callable] = {}
        self._tab_buttons: list[QPushButton] = []
        self._sim_scans: list[dict] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setObjectName("contentArea")
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        enable_touch_scroll(self.scroll)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(8, 8, 8, 8)
        inner_layout.setSpacing(12)
        inner_layout.addWidget(self._build_meta_strip())
        inner_layout.addWidget(self._build_stat_row())
        inner_layout.addWidget(self._build_tab_bar())

        self.section_stack = QStackedWidget()
        self.section_stack.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.MinimumExpanding,
        )
        for _label, tile_specs in _TILE_DEFS:
            self.section_stack.addWidget(self._build_section_page(tile_specs))
        inner_layout.addWidget(self.section_stack)

        inner_layout.addWidget(self._build_sim_section())
        inner_layout.addStretch(1)

        self.scroll.setWidget(inner)
        outer.addWidget(self.scroll)

        self._select_tab(0)

        state.case_info_changed.connect(self._refresh_meta)
        state.evidence_changed.connect(self._refresh_counts)
        self._refresh_meta(state.case_info or {})
        self._refresh_counts(state.evidence or {})

    def _build_meta_strip(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("roundCard")
        apply_card_shadow(frame)
        row = QHBoxLayout(frame)
        row.setContentsMargins(18, 12, 18, 12)
        row.setSpacing(20)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.meta_number = QLabel(" - ")
        self.meta_number.setObjectName("caseCardNumber")
        text_col.addWidget(self.meta_number)
        self.meta_name = QLabel("(no case)")
        self.meta_name.setObjectName("caseCardName")
        text_col.addWidget(self.meta_name)
        self.meta_examiner = QLabel("")
        self.meta_examiner.setObjectName("caseCardMeta")
        text_col.addWidget(self.meta_examiner)
        row.addLayout(text_col, 1)

        self.integrity_badge = QLabel("UNVERIFIED")
        self.integrity_badge.setObjectName("badgeGray")
        self.integrity_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.integrity_badge, 0, Qt.AlignmentFlag.AlignTop)
        return frame

    def _build_stat_row(self) -> QWidget:
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACING_TILE)
        for key, label in (
            ("artifacts", "Total Artifacts"),
            ("messages",  "Messages"),
            ("calls",     "Calls"),
            ("contacts",  "Contacts"),
        ):
            row.addWidget(self._stat_card(key, label), 1)
        return host

    def _stat_card(self, key: str, label: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("statCardLg")
        frame.setMinimumWidth(0)
        apply_card_shadow(frame)
        col = QVBoxLayout(frame)
        col.setContentsMargins(14, 10, 14, 10)
        col.setSpacing(2)
        value = QLabel("0")
        value.setObjectName("statCardLgValue")
        col.addWidget(value)
        lbl = QLabel(label)
        lbl.setObjectName("statCardLgLabel")
        col.addWidget(lbl)
        self._stat_value_labels[key] = value
        return frame

    def _build_tab_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("tabBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(bar)
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(4)
        for idx, (label, _specs) in enumerate(_TILE_DEFS):
            btn = QPushButton(label)
            btn.setObjectName("tabInactive")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked, i=idx: self._select_tab(i))
            self._tab_buttons.append(btn)
            row.addWidget(btn)
        row.addStretch(1)
        return bar

    def _select_tab(self, index: int) -> None:
        if not (0 <= index < self.section_stack.count()):
            return
        t0 = time.perf_counter()
        self.section_stack.setCurrentIndex(index)
        for i, btn in enumerate(self._tab_buttons):
            btn.setObjectName("tabActive" if i == index else "tabInactive")
            style = btn.style()
            style.unpolish(btn)
            style.polish(btn)
        print(
            f"[dash] _select_tab({index}): "
            f"{(time.perf_counter() - t0) * 1000:.1f}ms"
        )

    def _build_section_page(self, tile_specs: list[tuple]) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 8, 0, 0)
        page_layout.setSpacing(0)

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(SPACING_TILE)
        self._populate_grid(grid, tile_specs)
        page_layout.addWidget(grid_host)
        page_layout.addStretch(1)
        return page

    def _populate_grid(self, grid: QGridLayout, tile_specs: list[tuple]) -> None:
        cols = 2
        for idx, (page_id, icon, label, resolver, disabled) in enumerate(tile_specs):
            tile = Tile(
                page_id=page_id,
                icon_name=icon,
                label=label,
                count=None,
                disabled=disabled,
            )
            tile.tile_clicked.connect(self.navigate_requested.emit)
            r, c = divmod(idx, cols)
            grid.addWidget(tile, r, c)
            self._tile_resolvers[tile] = resolver

    def _refresh_meta(self, info: dict) -> None:
        info = info or {}
        self.meta_number.setText(info.get("case_number", " - "))
        self.meta_name.setText(info.get("name", "(no case)"))
        ex = info.get("examiner") or ""
        st = (info.get("status") or "").upper()
        self.meta_examiner.setText(" · ".join(x for x in (ex, st) if x))
        if info.get("integrity_verified"):
            self.integrity_badge.setText("VERIFIED")
            self.integrity_badge.setObjectName("badgeGreen")
        else:
            self.integrity_badge.setText("UNVERIFIED")
            self.integrity_badge.setObjectName("badgeGray")
        self.integrity_badge.style().unpolish(self.integrity_badge)
        self.integrity_badge.style().polish(self.integrity_badge)

    def _refresh_counts(self, evidence: dict) -> None:
        evidence = evidence or {}
        categories = evidence.get("categories") or {}
        message_sources = evidence.get("message_sources") or {}
        photos = evidence.get("photos", 0) or 0

        total = evidence.get("total_artifacts", sum(
            v for v in categories.values() if isinstance(v, int)
        ))
        self._stat_value_labels["artifacts"].setText(fmt(total))
        self._stat_value_labels["messages"].setText(fmt(categories.get("messages", 0)))
        self._stat_value_labels["calls"].setText(fmt(categories.get("calls", 0)))
        self._stat_value_labels["contacts"].setText(fmt(categories.get("contacts", 0)))

        for tile, resolver in self._tile_resolvers.items():
            try:
                count = resolver(categories, message_sources, photos)
            except Exception:
                count = None
            tile.set_count(count)

    def _build_sim_section(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("roundCard")
        apply_card_shadow(frame)
        col = QVBoxLayout(frame)
        col.setContentsMargins(14, 12, 14, 12)
        col.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("SIM Extractions")
        title.setStyleSheet(
            "font-size: 14px; font-weight: 700; background: transparent;"
        )
        header.addWidget(title)
        self._sim_count_lbl = QLabel("")
        self._sim_count_lbl.setObjectName("mutedText")
        self._sim_count_lbl.setStyleSheet(
            "background: transparent; padding-left: 6px;"
        )
        header.addWidget(self._sim_count_lbl)
        header.addStretch(1)
        scan_btn = QPushButton("+ Scan New SIM")
        scan_btn.setObjectName("pillCreate")
        scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        scan_btn.setMinimumHeight(36)
        scan_btn.clicked.connect(lambda: self.sim_scan_requested.emit(None))
        header.addWidget(scan_btn)
        col.addLayout(header)

        self._sim_list_layout = QVBoxLayout()
        self._sim_list_layout.setContentsMargins(0, 0, 0, 0)
        self._sim_list_layout.setSpacing(6)
        col.addLayout(self._sim_list_layout)

        return frame

    def _render_sim_section(self) -> None:
        while self._sim_list_layout.count():
            item = self._sim_list_layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        scans = self._sim_scans
        n = len(scans)
        self._sim_count_lbl.setText(f"{n} scan" + ("" if n == 1 else "s"))
        if not scans:
            empty = QLabel(
                "No SIM extractions yet. Tap + Scan New SIM to begin."
            )
            empty.setObjectName("mutedText")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                "background: transparent; padding: 20px 0;"
            )
            self._sim_list_layout.addWidget(empty)
            return
        for scan in scans:
            row = _build_sim_scan_row(scan)
            row.clicked.connect(self._on_sim_row_clicked)
            self._sim_list_layout.addWidget(row)

    def _on_sim_row_clicked(self, scan: dict) -> None:
        scan_id = scan.get("scan_id")
        if scan_id:
            self.sim_scan_requested.emit(scan_id)

    def _load_sim_scans(self) -> None:
        if not self.state.case_id:
            self._sim_scans = []
            self._render_sim_section()
            return
        api.run_async(
            api.get,
            on_result=self._on_sim_scans_loaded,
            on_error=lambda _msg: self._on_sim_scans_loaded({"scans": []}),
            path=f"/sim/case/{self.state.case_id}",
        )

    def _on_sim_scans_loaded(self, data) -> None:
        scans = list((data or {}).get("scans") or [])
        self._sim_scans = scans
        self._render_sim_section()

    def on_show(self) -> None:
        self._load_sim_scans()


def _build_sim_scan_row(scan: dict) -> ListRow:
    op_country_parts: list[str] = []
    if scan.get("operator_name"):
        op_country_parts.append(str(scan["operator_name"]))
    if scan.get("country") and scan.get("country") != scan.get("operator_name"):
        op_country_parts.append(str(scan["country"]))
    primary = QLabel(" · ".join(op_country_parts) or "(unknown carrier)")
    primary.setStyleSheet(
        f"QLabel {{"
        f"  font-size: {TYPE_MD}px;"
        f"  font-weight: 600;"
        f"  color: {TEXT_PRIMARY};"
        f"  background: transparent;"
        f"  border: none;"
        f"}}"
    )
    primary.setWordWrap(True)
    primary.setSizePolicy(
        QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
    )
    primary.setMinimumHeight(0)
    body_widgets: list[QWidget] = [primary]

    ids_parts: list[str] = []
    if scan.get("imsi"):
        ids_parts.append(f"IMSI {scan['imsi']}")
    iccid = scan.get("iccid") or ""
    if iccid:
        tail = iccid if len(iccid) <= 12 else f"…{iccid[-8:]}"
        ids_parts.append(f"ICCID {tail}")
    if ids_parts:
        ids = QLabel(" · ".join(ids_parts))
        ids.setStyleSheet(
            f"QLabel {{"
            f"  font-family: 'JetBrains Mono','Consolas',monospace;"
            f"  font-size: {TYPE_XS}px;"
            f"  color: {TEXT_SECONDARY};"
            f"  background: transparent;"
            f"  border: none;"
            f"}}"
        )
        ids.setWordWrap(True)
        ids.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        ids.setMinimumHeight(0)
        body_widgets.append(ids)

    scanned = scan.get("scanned_at") or ""
    if scanned:
        try:
            dt = datetime.fromisoformat(scanned)
            ts = dt.strftime("%Y-%m-%d %H:%M UTC")
        except (TypeError, ValueError):
            ts = scanned
        ts_lbl = QLabel(f"Scanned: {ts}")
        ts_lbl.setStyleSheet(
            f"QLabel {{"
            f"  font-size: {TYPE_XS}px;"
            f"  color: {TEXT_MUTED};"
            f"  background: transparent;"
            f"  border: none;"
            f"}}"
        )
        body_widgets.append(ts_lbl)

    return ListRow(
        body_widgets,
        evidence_band=True,
        payload=scan,
    )

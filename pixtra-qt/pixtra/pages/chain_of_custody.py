from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import api, icons
from ..format import fmt, fmt_bytes, fmt_time
from ..state import AppState
from ..theme import GREEN_700, apply_card_shadow
from ..touch import enable_touch_scroll


ACTION_ICONS = {
    "case_created": "folder_plus",
    "extraction_started": "download",
    "extraction_complete": "check_circle",
    "evidence_accessed": "search",
    "report_generated": "file_text",
    "integrity_verified": "lock",
    "hash_verified": "shield_check",
    "hash_mismatch": "alert_triangle",
}
DEFAULT_ACTION_ICON = "clipboard"

EM_DASH = " - "

_STATUS_GLYPHS = {"ok": "✓", "mismatch": "✗", "missing": "?"}
_STATUS_COLORS = {
    "ok": GREEN_700,
    "mismatch": "#C62828",
    "missing": "#E65100",
}


def _humanize(action: str) -> str:
    return (action or "").replace("_", " ").title()


def _short(h: Optional[str], width: int = 16) -> str:
    if not h:
        return EM_DASH
    return h if len(h) <= width else f"{h[:width]}…"


class ChainOfCustodyPage(QWidget):
    MANIFEST_PAGE_SIZE = 200

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._acq_id: Optional[str] = None
        self._log_entries: list[dict] = []
        self._manifest: list[dict] = []
        self._manifest_shown = 0
        self._verify_status: dict[str, str] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        tab_row = QHBoxLayout()
        tab_row.setSpacing(6)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._tab_buttons: list[QPushButton] = []
        for label, idx in (("Activity Log", 0), ("Hash Manifest", 1)):
            btn = QPushButton(label)
            btn.setObjectName("chipFilter")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if idx == 0:
                btn.setChecked(True)
            btn.clicked.connect(lambda _checked, i=idx: self._set_tab(i))
            self._tab_group.addButton(btn)
            self._tab_buttons.append(btn)
            tab_row.addWidget(btn)
        tab_row.addStretch(1)

        self.reverify_btn = QPushButton("Re-verify")
        self.reverify_btn.setObjectName("pillCreate")
        self.reverify_btn.setIcon(icons.qicon("refresh", size=14, color="#FFFFFF"))
        self.reverify_btn.setIconSize(icons.icon_size(14))
        self.reverify_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reverify_btn.clicked.connect(self._reverify)
        self.reverify_btn.setEnabled(False)
        tab_row.addWidget(self.reverify_btn)
        root.addLayout(tab_row)

        self.verify_result = QLabel("")
        self.verify_result.setObjectName("mutedText")
        self.verify_result.setWordWrap(True)
        self.verify_result.setVisible(False)
        root.addWidget(self.verify_result)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_log_tab())
        self.stack.addWidget(self._build_manifest_tab())
        root.addWidget(self.stack, 1)

        state.case_changed.connect(lambda _: self._load_all())

    def on_show(self) -> None:
        self._load_all()

    def _build_log_tab(self) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        self.log_scroll = QScrollArea()
        self.log_scroll.setWidgetResizable(True)
        self.log_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.log_scroll.setObjectName("contentArea")
        self.log_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        enable_touch_scroll(self.log_scroll)
        self.log_inner = QWidget()
        self.log_layout = QVBoxLayout(self.log_inner)
        self.log_layout.setContentsMargins(8, 8, 8, 8)
        self.log_layout.setSpacing(0)
        self.log_layout.addStretch()
        self.log_scroll.setWidget(self.log_inner)
        col.addWidget(self.log_scroll, 1)

        return page

    def _build_manifest_tab(self) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(6)

        self.manifest_meta = QLabel("")
        self.manifest_meta.setObjectName("mutedText")
        self.manifest_meta.setStyleSheet(
            "background: transparent; padding: 0 4px;"
        )
        self.manifest_meta.setWordWrap(True)
        col.addWidget(self.manifest_meta)

        self.manifest_scroll = QScrollArea()
        self.manifest_scroll.setWidgetResizable(True)
        self.manifest_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.manifest_scroll.setObjectName("contentArea")
        self.manifest_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        enable_touch_scroll(self.manifest_scroll)
        self.manifest_inner = QWidget()
        self.manifest_layout = QVBoxLayout(self.manifest_inner)
        self.manifest_layout.setContentsMargins(0, 4, 0, 4)
        self.manifest_layout.setSpacing(8)
        self.manifest_layout.addStretch()
        self.manifest_scroll.setWidget(self.manifest_inner)
        col.addWidget(self.manifest_scroll, 1)

        self.manifest_scroll.verticalScrollBar().valueChanged.connect(
            self._on_manifest_scrolled
        )

        return page

    def _set_tab(self, index: int) -> None:
        self.stack.setCurrentIndex(index)

    def _load_all(self) -> None:
        self._load_log()
        self._load_acquisition()

    def _load_log(self) -> None:
        if not self.state.case_id:
            return
        api.run_async(
            api.get,
            on_result=self._on_log_loaded,
            on_error=lambda _msg: None,
            path=f"/cases/{self.state.case_id}/custody",
        )

    def _load_acquisition(self) -> None:
        if not self.state.case_id:
            self._set_manifest_empty("No case selected")
            return
        api.run_async(
            api.get,
            on_result=self._on_acquisitions_loaded,
            on_error=lambda msg: self._set_manifest_empty(
                f"Failed to load: {msg}"
            ),
            path=f"/acquisitions/case/{self.state.case_id}",
        )

    def _on_log_loaded(self, data) -> None:
        entries = api.coerce_list(data, "chain", "entries", "items", "custody")
        self._log_entries = entries
        self._render_log()

    def _render_log(self) -> None:
        self._clear_layout(self.log_layout, keep_trailing_stretch=False)
        if not self._log_entries:
            wrap = QWidget()
            wl = QVBoxLayout(wrap)
            wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ic = QLabel()
            ic.setPixmap(
                icons.pixmap("shield_check", size=40, color="#98988F", stroke=1.5)
            )
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            wl.addWidget(ic)
            msg = QLabel("No entries")
            msg.setObjectName("mutedText")
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            wl.addWidget(msg)
            self.log_layout.addWidget(wrap)
            self.log_layout.addStretch()
            return

        for i, e in enumerate(self._log_entries):
            self.log_layout.addWidget(
                self._log_row(e, last=i == len(self._log_entries) - 1)
            )
        self.log_layout.addStretch()

    def _log_row(self, e: dict, last: bool) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background: transparent; border-bottom: 1px solid #F0F0EA; }"
        )
        row = QHBoxLayout(frame)
        row.setContentsMargins(0, 10, 0, 10)
        row.setSpacing(12)

        dot_col = QVBoxLayout()
        dot_col.setContentsMargins(0, 2, 0, 0)
        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet("background: #2A9461; border: 2px solid #D4EDDF;")
        dot_col.addWidget(dot)
        if not last:
            connector = QFrame()
            connector.setFixedWidth(2)
            connector.setStyleSheet("background: #E8E8E2;")
            dot_col.addWidget(connector, 1)
        else:
            dot_col.addStretch()
        row.addLayout(dot_col)

        body = QVBoxLayout()
        body.setSpacing(2)
        head = QHBoxLayout()
        head.setSpacing(6)
        icon_name = ACTION_ICONS.get(e.get("action"), DEFAULT_ACTION_ICON)
        ic = QLabel()
        ic.setFixedSize(14, 14)
        ic.setPixmap(icons.pixmap(icon_name, size=14, color="#1B5E3B"))
        head.addWidget(ic)
        name = QLabel(_humanize(e.get("action") or ""))
        name.setStyleSheet(
            "font-size: 13px; font-weight: 600; background: transparent;"
        )
        head.addWidget(name)
        head.addStretch()
        ts = QLabel(fmt_time(e.get("timestamp") or e.get("created_at")))
        ts.setObjectName("subtle")
        head.addWidget(ts)
        body.addLayout(head)

        details = []
        if e.get("examiner"):
            details.append(f"By: {e['examiner']}")
        if e.get("details"):
            details.append(e["details"])
        if details:
            d = QLabel(" - ".join(details))
            d.setObjectName("mutedText")
            d.setWordWrap(True)
            body.addWidget(d)

        if e.get("hash") or e.get("file_hash"):
            h = QLabel(f"SHA256: {e.get('hash') or e.get('file_hash')}")
            h.setObjectName("monoSm")
            h.setWordWrap(True)
            body.addWidget(h)

        row.addLayout(body, 1)
        return frame

    def _on_acquisitions_loaded(self, data) -> None:
        acqs = api.coerce_list(data, "acquisitions", "items")
        if not acqs:
            self._set_manifest_empty("No acquisitions for this case yet")
            return
        self._acq_id = acqs[0].get("id")
        if not self._acq_id:
            self._set_manifest_empty("Acquisition row missing id")
            return
        self.manifest_meta.setText(
            f"Acquisition {self._acq_id} · {acqs[0].get('method', '')}"
        )
        api.run_async(
            api.get,
            on_result=self._on_manifest_loaded,
            on_error=lambda msg: self._set_manifest_empty(
                f"Failed to load manifest: {msg}"
            ),
            path=f"/acquisitions/{self._acq_id}/hashes",
        )

    def _on_manifest_loaded(self, data) -> None:
        rows = api.coerce_list(data, "files", "manifest", "items")
        self._manifest = rows
        self._manifest_shown = min(self.MANIFEST_PAGE_SIZE, len(rows))
        self._render_manifest()
        self.reverify_btn.setEnabled(self._acq_id is not None)
        if self._acq_id:
            self.manifest_meta.setText(
                f"Acquisition {self._acq_id} · {fmt(len(rows))} files"
            )

    def _set_manifest_empty(self, message: str) -> None:
        self._acq_id = None
        self._manifest = []
        self._manifest_shown = 0
        self.manifest_meta.setText(message)
        self._render_manifest()
        self.reverify_btn.setEnabled(False)

    def _render_manifest(self) -> None:
        self._clear_layout(self.manifest_layout, keep_trailing_stretch=False)

        if not self._manifest:
            empty = QLabel("No manifest rows yet")
            empty.setObjectName("mutedText")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("background: transparent; padding: 32px 0;")
            self.manifest_layout.addWidget(empty)
            self.manifest_layout.addStretch()
            return

        for row in self._manifest[: self._manifest_shown]:
            self.manifest_layout.addWidget(self._hash_row(row))
        self.manifest_layout.addStretch()

        self._update_manifest_meta()

    def _update_manifest_meta(self) -> None:
        if not self._acq_id:
            return
        total = len(self._manifest)
        if self._manifest_shown < total:
            self.manifest_meta.setText(
                f"Acquisition {self._acq_id} · "
                f"{fmt(self._manifest_shown)} of {fmt(total)} files"
            )
        else:
            self.manifest_meta.setText(
                f"Acquisition {self._acq_id} · {fmt(total)} files"
            )

    def _reveal_more_manifest(self) -> None:
        prev_shown = self._manifest_shown
        new_shown = min(
            self._manifest_shown + self.MANIFEST_PAGE_SIZE,
            len(self._manifest),
        )
        if new_shown == prev_shown:
            return
        for row in self._manifest[prev_shown:new_shown]:
            self.manifest_layout.insertWidget(
                self.manifest_layout.count() - 1, self._hash_row(row)
            )
        self._manifest_shown = new_shown
        self._update_manifest_meta()

    def _on_manifest_scrolled(self, value: int) -> None:
        sb = self.manifest_scroll.verticalScrollBar()
        max_val = sb.maximum()
        if max_val <= 0:
            return
        if value < max_val - 200:
            return
        if self._manifest_shown >= len(self._manifest):
            return
        self._reveal_more_manifest()

    def _hash_row(self, row: dict) -> QFrame:
        fpath = row.get("file_path") or row.get("path") or ""
        md5 = row.get("md5")
        sha1 = row.get("sha1")
        sha256 = row.get("sha256")
        size = row.get("size_bytes") or 0
        status = self._verify_status.get(fpath, "")

        frame = QFrame()
        frame.setObjectName("caseCard")
        rl = QVBoxLayout(frame)
        rl.setContentsMargins(14, 10, 14, 10)
        rl.setSpacing(2)

        head = QHBoxLayout()
        name = QLabel(fpath or "(no path)")
        name.setStyleSheet(
            "font-size: 13px; font-weight: 600; background: transparent;"
        )
        name.setWordWrap(True)
        head.addWidget(name, 1)

        glyph = _STATUS_GLYPHS.get(status, EM_DASH)
        glyph_color = _STATUS_COLORS.get(status, "#7A7A72")
        status_lbl = QLabel(glyph)
        status_lbl.setStyleSheet(
            f"color: {glyph_color}; font-size: 16px; font-weight: 700; "
            "background: transparent;"
        )
        status_lbl.setToolTip(status or "Not yet verified")
        head.addWidget(status_lbl)
        rl.addLayout(head)

        meta = QLabel(
            f"{fmt_bytes(size)}  ·  MD5 {_short(md5, 12)}  "
            f"·  SHA-1 {_short(sha1, 12)}"
        )
        meta.setObjectName("subtle")
        meta.setWordWrap(True)
        rl.addWidget(meta)

        sha256_lbl = QLabel(f"SHA-256: {sha256}" if sha256 else "SHA-256:  - ")
        sha256_lbl.setObjectName("monoSm")
        sha256_lbl.setWordWrap(True)
        rl.addWidget(sha256_lbl)

        apply_card_shadow(frame)
        return frame

    def _reverify(self) -> None:
        if not self._acq_id:
            return
        self.reverify_btn.setEnabled(False)
        self.verify_result.setVisible(True)
        self.verify_result.setStyleSheet(
            "color: #62625F; background: transparent;"
        )
        self.verify_result.setText(
            "Re-hashing every file in the acquisition output..."
        )
        api.run_async(
            api.post,
            on_result=self._on_reverify_ok,
            on_error=self._on_reverify_err,
            path=f"/acquisitions/{self._acq_id}/reverify-hashes",
        )

    def _on_reverify_ok(self, data) -> None:
        self.reverify_btn.setEnabled(True)
        data = data if isinstance(data, dict) else {}
        verified = int(data.get("verified", 0))
        mismatched = int(data.get("mismatched", 0))
        missing = int(data.get("missing", 0))

        self._verify_status.clear()
        for entry in data.get("mismatch_details") or []:
            p = entry.get("file_path") or entry.get("path")
            if p:
                self._verify_status[p] = entry.get("status") or "mismatch"
        for row in self._manifest:
            p = row.get("file_path") or row.get("path") or ""
            self._verify_status.setdefault(p, "ok")

        if mismatched == 0 and missing == 0:
            self.verify_result.setStyleSheet(
                "color: #14432A; background: #D4EDDF; padding: 6px 10px;"
            )
            self.verify_result.setText(
                f"Integrity verified - {verified} file(s) match the manifest"
            )
        else:
            self.verify_result.setStyleSheet(
                "color: #C62828; background: #FDECEA; padding: 6px 10px;"
            )
            self.verify_result.setText(
                f"Integrity check failed - verified={verified}, "
                f"mismatched={mismatched}, missing={missing}"
            )

        api.run_async(
            api.get,
            on_result=self._on_manifest_loaded,
            on_error=lambda _msg: None,
            path=f"/acquisitions/{self._acq_id}/hashes",
        )
        self._load_log()

    def _on_reverify_err(self, msg: str) -> None:
        self.reverify_btn.setEnabled(True)
        self.verify_result.setStyleSheet(
            "color: #C62828; background: #FDECEA; padding: 6px 10px;"
        )
        self.verify_result.setText(f"Re-verify failed: {msg}")

    @staticmethod
    def _clear_layout(layout: QVBoxLayout, *, keep_trailing_stretch: bool) -> None:
        end = 1 if keep_trailing_stretch and layout.count() > 0 else 0
        while layout.count() > end:
            item = layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import api, icons
from ..state import AppState
from ..theme import GREEN_700, apply_card_shadow
from ..touch import enable_touch_scroll


_TOUCH_HEIGHT = 44


def _fmt_scan_time(iso: Optional[str]) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (TypeError, ValueError):
        return iso


def _dot(color_hex: str) -> QLabel:
    lbl = QLabel()
    lbl.setFixedSize(10, 10)
    lbl.setStyleSheet(
        f"QLabel {{ background: {color_hex}; border-radius: 5px; }}"
    )
    return lbl


class SimPage(QWidget):
    navigate_requested = pyqtSignal(str)
    toast = pyqtSignal(str)
    scan_completed = pyqtSignal()

    wizard_origin = "dashboard"

    @property
    def is_wizard(self) -> bool:
        return self._mode == "scan"

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._mode: str = "scan"
        self._scan_id: Optional[str] = None
        self._reader_status: dict = {}
        self._current_scan: Optional[dict] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setObjectName("contentArea")
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        enable_touch_scroll(self.scroll)

        host = QWidget()
        col = QVBoxLayout(host)
        col.setContentsMargins(8, 8, 8, 8)
        col.setSpacing(10)

        title_row = QHBoxLayout()
        self.title_lbl = QLabel("New SIM Extraction")
        self.title_lbl.setStyleSheet(
            "font-size: 22px; font-weight: 800; background: transparent;"
        )
        title_row.addWidget(self.title_lbl)
        title_row.addStretch(1)
        col.addLayout(title_row)

        self.case_banner = QFrame()
        self.case_banner.setStyleSheet(
            "QFrame { background: #E8F4ED; border: 1px solid #B7DCC4; "
            "border-radius: 8px; }"
        )
        bl = QHBoxLayout(self.case_banner)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.setSpacing(8)
        bl_icon = QLabel()
        bl_icon.setPixmap(icons.pixmap("folder_open", size=16, color=GREEN_700))
        bl_icon.setStyleSheet("background: transparent; border: none;")
        bl.addWidget(bl_icon)
        self.case_banner_lbl = QLabel("Attaching to case:  - ")
        self.case_banner_lbl.setStyleSheet(
            f"color: #14432A; font-size: 12px; font-weight: 600; "
            f"background: transparent; border: none;"
        )
        bl.addWidget(self.case_banner_lbl, 1)
        col.addWidget(self.case_banner)

        self.status_card = QFrame()
        self.status_card.setStyleSheet(
            "QFrame { background: #FFFFFF; border: 1px solid #E8E8E2; "
            f"border-left: 4px solid {GREEN_700}; border-radius: 8px; }}"
        )
        sl = QVBoxLayout(self.status_card)
        sl.setContentsMargins(12, 8, 12, 8)
        sl.setSpacing(4)

        reader_row = QHBoxLayout()
        reader_row.setSpacing(8)
        self._reader_dot = _dot("#C62828")
        reader_row.addWidget(self._reader_dot)
        self.reader_label = QLabel("Reader: probing…")
        self.reader_label.setStyleSheet(
            "font-size: 12px; background: transparent; border: none;"
        )
        reader_row.addWidget(self.reader_label, 1)
        sl.addLayout(reader_row)

        card_row = QHBoxLayout()
        card_row.setSpacing(8)
        self._card_dot = _dot("#C62828")
        card_row.addWidget(self._card_dot)
        self.card_label = QLabel("Card: probing…")
        self.card_label.setStyleSheet(
            "font-size: 12px; background: transparent; border: none;"
        )
        card_row.addWidget(self.card_label, 1)
        sl.addLayout(card_row)
        col.addWidget(self.status_card)

        scan_row = QHBoxLayout()
        self.scan_btn = QPushButton("Scan SIM")
        self.scan_btn.setObjectName("pillCreate")
        self.scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scan_btn.setMinimumHeight(_TOUCH_HEIGHT)
        self.scan_btn.setMinimumWidth(180)
        self.scan_btn.clicked.connect(self._on_scan_clicked)
        self.scan_btn.setEnabled(False)
        scan_row.addWidget(self.scan_btn)
        scan_row.addStretch(1)
        self.refresh_btn = QPushButton("Refresh reader")
        self.refresh_btn.setObjectName("btnGhost")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setMinimumHeight(_TOUCH_HEIGHT)
        self.refresh_btn.clicked.connect(self._refresh_status)
        scan_row.addWidget(self.refresh_btn)
        scan_row_widget = QWidget()
        scan_row_widget.setLayout(scan_row)
        col.addWidget(scan_row_widget)
        self._scan_row_widget = scan_row_widget

        self.result_frame = QFrame()
        self.result_frame.setObjectName("roundCard")
        apply_card_shadow(self.result_frame)
        self.result_layout = QVBoxLayout(self.result_frame)
        self.result_layout.setContentsMargins(14, 12, 14, 12)
        self.result_layout.setSpacing(8)
        self._render_result_placeholder()
        col.addWidget(self.result_frame)

        self.apdus_frame = QFrame()
        self.apdus_frame.setObjectName("roundCard")
        apply_card_shadow(self.apdus_frame)
        af = QVBoxLayout(self.apdus_frame)
        af.setContentsMargins(14, 12, 14, 12)
        af.setSpacing(6)
        self.apdus_toggle = QPushButton("View raw APDUs")
        self.apdus_toggle.setObjectName("btnGhost")
        self.apdus_toggle.setCheckable(True)
        self.apdus_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apdus_toggle.setMinimumHeight(36)
        self.apdus_toggle.toggled.connect(self._on_apdus_toggled)
        af.addWidget(self.apdus_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.apdus_body = QLabel("")
        self.apdus_body.setStyleSheet(
            "font-family: 'JetBrains Mono','Consolas',monospace; "
            "font-size: 11px; color: #1C1C1A; "
            "background: #FAFAF7; padding: 8px; border: 1px solid #E8E8E2;"
        )
        self.apdus_body.setWordWrap(True)
        self.apdus_body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.apdus_body.setVisible(False)
        af.addWidget(self.apdus_body)
        col.addWidget(self.apdus_frame)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.done_btn = QPushButton("Done")
        self.done_btn.setObjectName("pillCreate")
        self.done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.done_btn.setMinimumHeight(_TOUCH_HEIGHT)
        self.done_btn.setMinimumWidth(120)
        self.done_btn.clicked.connect(self._on_done_clicked)
        self.done_btn.setVisible(False)
        action_row.addWidget(self.done_btn)
        action_row.addStretch(1)
        self.delete_btn = QPushButton("Delete this scan")
        self.delete_btn.setObjectName("btnGhost")
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.setMinimumHeight(_TOUCH_HEIGHT)
        self.delete_btn.setStyleSheet(
            "QPushButton#btnGhost { color: #C62828; }"
        )
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        action_row.addWidget(self.delete_btn)
        action_row_widget = QWidget()
        action_row_widget.setLayout(action_row)
        col.addWidget(action_row_widget)
        self._action_row_widget = action_row_widget

        col.addStretch(1)

        self.scroll.setWidget(host)
        outer.addWidget(self.scroll)

        self._apply_mode_visibility()

    def set_mode(self, mode: str, scan_id: Optional[str] = None) -> None:
        self._mode = mode if mode in ("scan", "detail") else "scan"
        self._scan_id = scan_id
        self._current_scan = None
        self._apply_mode_visibility()

    def _apply_mode_visibility(self) -> None:
        is_scan = self._mode == "scan"
        is_detail = self._mode == "detail"
        self.case_banner.setVisible(is_scan)
        self.status_card.setVisible(is_scan)
        self._scan_row_widget.setVisible(is_scan)
        self.done_btn.setVisible(is_scan)
        self.apdus_frame.setVisible(is_detail)
        self.delete_btn.setVisible(is_detail)
        if is_scan:
            self.title_lbl.setText("New SIM Extraction")
        else:
            short = (self._scan_id or "")[:12]
            self.title_lbl.setText(
                f"SIM Extraction · {short}" if short else "SIM Extraction"
            )

    def on_show(self) -> None:
        if self._mode == "scan":
            self._refresh_status()
            self._render_result_placeholder()
            self._update_case_banner()
        else:
            self._load_scan_detail()

    def _update_case_banner(self) -> None:
        info = self.state.case_info or {}
        name = info.get("name") or self.state.case_id or " - "
        self.case_banner_lbl.setText(f"Attaching to case: {name}")

    def _refresh_status(self) -> None:
        api.run_async(
            api.get,
            on_result=self._on_status,
            on_error=self._on_status_error,
            path="/sim/reader/status",
        )

    def _on_status(self, data) -> None:
        if not isinstance(data, dict):
            data = {}
        self._reader_status = data
        has_reader = bool(data.get("has_reader"))
        has_card = bool(data.get("has_card"))
        reader_name = data.get("reader_name") or " - "
        if has_reader:
            self._reader_dot.setStyleSheet(
                "QLabel { background: #2A9461; border-radius: 5px; }"
            )
            self.reader_label.setText(f"Reader: connected - {reader_name}")
        else:
            self._reader_dot.setStyleSheet(
                "QLabel { background: #C62828; border-radius: 5px; }"
            )
            self.reader_label.setText(
                "Reader: not detected - check USB connection"
            )
        if has_card:
            self._card_dot.setStyleSheet(
                "QLabel { background: #2A9461; border-radius: 5px; }"
            )
            self.card_label.setText("Card: inserted")
        else:
            self._card_dot.setStyleSheet(
                "QLabel { background: #C62828; border-radius: 5px; }"
            )
            self.card_label.setText(
                "Card: not inserted" if has_reader else "Card:  - "
            )
        ready = has_reader and has_card and bool(self.state.case_id)
        self.scan_btn.setEnabled(ready)
        if not self.state.case_id:
            self.scan_btn.setToolTip("Open a case first")
        elif not has_reader:
            self.scan_btn.setToolTip("USB smart-card reader not detected")
        elif not has_card:
            self.scan_btn.setToolTip("Insert a SIM into the reader")
        else:
            self.scan_btn.setToolTip("")

    def _on_status_error(self, msg: str) -> None:
        self._reader_dot.setStyleSheet(
            "QLabel { background: #C62828; border-radius: 5px; }"
        )
        self.reader_label.setText(f"Reader: status check failed - {msg}")
        self._card_dot.setStyleSheet(
            "QLabel { background: #C62828; border-radius: 5px; }"
        )
        self.card_label.setText("Card:  - ")
        self.scan_btn.setEnabled(False)

    def _on_scan_clicked(self) -> None:
        if not self.state.case_id:
            self.toast.emit("Open a case first")
            return
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Scanning…")
        api.run_async(
            api.post,
            on_result=self._on_scan_result,
            on_error=self._on_scan_error,
            path="/sim/scan",
            body={"case_id": self.state.case_id},
        )

    def _on_scan_result(self, data) -> None:
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("Scan SIM")
        if not isinstance(data, dict):
            self.toast.emit("Unexpected scan response")
            return
        self._current_scan = data
        self._render_result()
        self.toast.emit("SIM scan saved to case")
        self.scan_completed.emit()

    def _on_scan_error(self, msg: str) -> None:
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("Scan SIM")
        self.toast.emit(f"Scan failed: {msg}")

    def _on_done_clicked(self) -> None:
        self.navigate_requested.emit("dashboard")

    def _load_scan_detail(self) -> None:
        if not self.state.case_id or not self._scan_id:
            self.toast.emit("Missing scan reference")
            return
        api.run_async(
            api.get,
            on_result=self._on_scan_list_loaded,
            on_error=lambda msg: self.toast.emit(f"Load failed: {msg}"),
            path=f"/sim/case/{self.state.case_id}",
        )

    def _on_scan_list_loaded(self, data) -> None:
        scans = list((data or {}).get("scans") or [])
        match = next(
            (s for s in scans if s.get("scan_id") == self._scan_id), None,
        )
        if not match:
            self.toast.emit("Scan no longer exists")
            self.navigate_requested.emit("dashboard")
            return
        self._current_scan = match
        self._render_result()
        self._render_apdus(match.get("raw_apdus") or [])

    def _on_apdus_toggled(self, checked: bool) -> None:
        self.apdus_body.setVisible(checked)
        self.apdus_toggle.setText(
            "Hide raw APDUs" if checked else "View raw APDUs"
        )

    def _render_apdus(self, apdus: list) -> None:
        if not apdus:
            self.apdus_body.setText("(no APDUs recorded)")
            return
        lines = []
        for entry in apdus:
            apdu = entry.get("apdu") or "?"
            sw = entry.get("sw") or "????"
            resp = entry.get("response") or ""
            line = f"> {apdu}\n  SW={sw}"
            if resp:
                line += f"  data={resp}"
            lines.append(line)
        self.apdus_body.setText("\n".join(lines))

    def _on_delete_clicked(self) -> None:
        if not self._scan_id or not self.state.case_id:
            return
        confirm = QMessageBox.question(
            self,
            "Delete SIM scan",
            "This permanently removes the scan from the case. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.delete_btn.setEnabled(False)
        self.delete_btn.setText("Deleting…")
        api.run_async(
            api.delete,
            on_result=self._on_delete_result,
            on_error=self._on_delete_error,
            path=f"/sim/scan/{self._scan_id}",
        )

    def _on_delete_result(self, _data) -> None:
        self.delete_btn.setEnabled(True)
        self.delete_btn.setText("Delete this scan")
        self.toast.emit("SIM scan deleted")
        self.scan_completed.emit()
        self.navigate_requested.emit("dashboard")

    def _on_delete_error(self, msg: str) -> None:
        self.delete_btn.setEnabled(True)
        self.delete_btn.setText("Delete this scan")
        self.toast.emit(f"Delete failed: {msg}")

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _render_result_placeholder(self) -> None:
        self._clear_layout(self.result_layout)
        if self._mode == "scan":
            msg_text = (
                "No scan yet. Insert a SIM into the reader and tap Scan SIM."
            )
        else:
            msg_text = "Loading scan…"
        title = QLabel("Result")
        title.setStyleSheet(
            f"color: {GREEN_700}; font-size: 12px; font-weight: 700; "
            f"letter-spacing: 0.5px; background: transparent;"
        )
        self.result_layout.addWidget(title)
        msg = QLabel(msg_text)
        msg.setObjectName("mutedText")
        msg.setWordWrap(True)
        self.result_layout.addWidget(msg)

    def _render_result(self) -> None:
        scan = self._current_scan
        if not scan:
            self._render_result_placeholder()
            return
        self._clear_layout(self.result_layout)

        title = QLabel("Result")
        title.setStyleSheet(
            f"color: {GREEN_700}; font-size: 12px; font-weight: 700; "
            f"letter-spacing: 0.5px; background: transparent;"
        )
        self.result_layout.addWidget(title)

        self.result_layout.addWidget(self._build_section(
            "Identity",
            [
                ("ATR", scan.get("atr") or " - ", True),
                ("ICCID", scan.get("iccid") or " - ", True),
                ("IMSI", scan.get("imsi") or " - ", True),
            ],
        ))

        carrier_rows: list[tuple[str, str, bool]] = [
            ("Country", scan.get("country") or " - ", False),
            ("Operator", scan.get("operator_name") or " - ", False),
            ("MCC", scan.get("mcc") or " - ", True),
            ("MNC", scan.get("mnc") or " - ", True),
            ("MSIN", scan.get("msin") or " - ", True),
        ]
        if scan.get("spn"):
            carrier_rows.append(("SPN", scan["spn"], False))
        self.result_layout.addWidget(self._build_section(
            "Carrier", carrier_rows,
        ))

        if scan.get("lai_mcc") or scan.get("lai_mnc") or scan.get("lai_lac"):
            lai_rows: list[tuple[str, str, bool]] = [
                ("LAI MCC", scan.get("lai_mcc") or " - ", True),
                ("LAI MNC", scan.get("lai_mnc") or " - ", True),
                ("LAC", scan.get("lai_lac") or " - ", True),
            ]
        else:
            lai_rows = [(
                "Status", "Not available on this SIM", False,
            )]
        self.result_layout.addWidget(self._build_section(
            "Last Network Connection", lai_rows,
        ))

        footer_parts = []
        if scan.get("scanned_at"):
            footer_parts.append(f"Scanned: {_fmt_scan_time(scan['scanned_at'])}")
        if scan.get("scan_id"):
            footer_parts.append(f"Scan ID: {scan['scan_id']}")
        if scan.get("pin_required"):
            footer_parts.append("PIN-locked card")
        if footer_parts:
            footer = QLabel(" · ".join(footer_parts))
            footer.setObjectName("subtle")
            footer.setWordWrap(True)
            self.result_layout.addWidget(footer)

    @staticmethod
    def _build_section(title: str, rows: list[tuple]) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background: #FAFAF7; border: 1px solid #E8E8E2; "
            "border-radius: 6px; }"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color: {GREEN_700}; font-size: 11px; font-weight: 700; "
            f"letter-spacing: 0.5px; background: transparent; border: none;"
        )
        layout.addWidget(title_lbl)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(2)
        for r, (label, value, monospace) in enumerate(rows):
            k = QLabel(label)
            k.setStyleSheet(
                "font-size: 11px; color: #666666; background: transparent; "
                "border: none;"
            )
            grid.addWidget(k, r, 0)
            v = QLabel(str(value))
            v.setWordWrap(True)
            v.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            if monospace:
                v.setStyleSheet(
                    "font-family: 'JetBrains Mono','Consolas',monospace; "
                    "font-size: 11px; color: #1C1C1A; "
                    "background: transparent; border: none;"
                )
            else:
                v.setStyleSheet(
                    "font-size: 12px; font-weight: 600; color: #1C1C1A; "
                    "background: transparent; border: none;"
                )
            grid.addWidget(v, r, 1)
        layout.addLayout(grid)
        return frame

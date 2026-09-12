from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import api, icons
from ..format import fmt, fmt_bytes
from ..services import session as session_svc
from ..state import AppState


class AcquirePage(QWidget):
    navigate_requested = pyqtSignal(str)
    toast = pyqtSignal(str)

    is_wizard = True
    wizard_origin = "cases"

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._devices: list[dict] = []
        self._acq_id: Optional[str] = None

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(3000)
        self._poll_timer.timeout.connect(self._poll_status)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        self.detect_card = QFrame()
        self.detect_card.setObjectName("card")
        dc_layout = QVBoxLayout(self.detect_card)
        dc_layout.setContentsMargins(14, 12, 14, 12)
        dc_layout.setSpacing(6)

        dc_head = QHBoxLayout()
        title1 = QLabel("1. Detect Device")
        title1.setObjectName("cardTitle")
        dc_head.addWidget(title1)
        dc_head.addStretch()
        self.rescan_btn = QPushButton("Rescan")
        self.rescan_btn.setObjectName("btnSm")
        self.rescan_btn.setStyleSheet("background:#EAEAE4; color:#62625F;")
        self.rescan_btn.clicked.connect(self.scan_devices)
        dc_head.addWidget(self.rescan_btn)
        dc_layout.addLayout(dc_head)

        self.device_list_layout = QVBoxLayout()
        self.device_list_layout.setSpacing(6)
        dc_layout.addLayout(self.device_list_layout)

        root.addWidget(self.detect_card)

        self.extract_card = QFrame()
        self.extract_card.setObjectName("card")
        ex_layout = QVBoxLayout(self.extract_card)
        ex_layout.setContentsMargins(14, 12, 14, 12)
        ex_layout.setSpacing(8)
        title2 = QLabel("2. Extract Data")
        title2.setObjectName("cardTitle")
        ex_layout.addWidget(title2)

        self.start_btn = QPushButton("  Start Extraction")
        self.start_btn.setObjectName("btnPrimary")
        self.start_btn.setIcon(icons.qicon("download", size=14, color="#FFFFFF"))
        self.start_btn.setIconSize(icons.icon_size(14))
        self.start_btn.clicked.connect(self.start_extraction)
        self.start_btn.setEnabled(False)
        ex_layout.addWidget(self.start_btn, 0, Qt.AlignmentFlag.AlignLeft)

        self.progress_block = QWidget()
        pb_layout = QVBoxLayout(self.progress_block)
        pb_layout.setContentsMargins(0, 4, 0, 0)
        pb_layout.setSpacing(4)
        self.status_label = QLabel("Status: starting")
        self.status_label.setStyleSheet("font-size: 13px; font-weight: 600; background: transparent;")
        pb_layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        pb_layout.addWidget(self.progress_bar)
        self.progress_sub = QLabel("")
        self.progress_sub.setObjectName("mutedText")
        pb_layout.addWidget(self.progress_sub)
        self.view_evidence_btn = QPushButton("View Evidence")
        self.view_evidence_btn.setObjectName("btnPrimary")
        self.view_evidence_btn.clicked.connect(lambda: self.navigate_requested.emit("messages"))
        self.view_evidence_btn.setVisible(False)
        pb_layout.addWidget(self.view_evidence_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self.progress_block.setVisible(False)
        ex_layout.addWidget(self.progress_block)

        root.addWidget(self.extract_card)
        root.addStretch()

        session_svc.signals().authenticated.connect(self._apply_role_guards)
        session_svc.signals().session_expired.connect(self._apply_role_guards)
        self._apply_role_guards()


    def on_show(self) -> None:
        self.scan_devices()

    def _apply_role_guards(self) -> None:
        if session_svc.is_viewer():
            self.start_btn.setVisible(False)

    def scan_devices(self) -> None:
        api.run_async(
            api.get,
            on_result=self._on_devices_loaded,
            on_error=lambda msg: self.toast.emit(f"Scan failed: {msg}"),
            path="/devices/detect",
        )

    def _on_devices_loaded(self, result) -> None:
        self._devices = result if isinstance(result, list) else (result or {}).get("devices", [])

        while self.device_list_layout.count():
            item = self.device_list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not self._devices:
            msg = QLabel("No device connected")
            msg.setObjectName("mutedText")
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.device_list_layout.addWidget(msg)
            self.start_btn.setEnabled(False)
            return

        self.start_btn.setEnabled(True)
        for d in self._devices:
            self.device_list_layout.addWidget(self._device_row(d))

    def _device_row(self, d: dict) -> QFrame:
        is_ios = (d.get("platform") or "").lower() == "ios"
        tint = "#1B5E3B" if is_ios else "#1565C0"

        frame = QFrame()
        frame.setStyleSheet(
            "background: #FAFAF8; border: 1px solid #E8E8E2;"
        )
        row = QHBoxLayout(frame)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(10)

        badge = QLabel()
        badge.setFixedSize(32, 32)
        badge.setPixmap(icons.pixmap("smartphone", size=20, color=tint))
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(badge)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        name = QLabel(d.get("model_name") or d.get("product_type") or "Device")
        name.setStyleSheet("font-size: 13px; font-weight: 600; background: transparent;")
        text_col.addWidget(name)
        meta = QLabel(f"{d.get('os_version', '')} · {d.get('chipset', '')}")
        meta.setObjectName("monoSm")
        text_col.addWidget(meta)
        row.addLayout(text_col, 1)

        tag = QLabel(d.get("recommended_method", "logical"))
        tag.setObjectName("badgeGreen")
        row.addWidget(tag)
        return frame

    def start_extraction(self) -> None:
        cid = self.state.case_id
        if not cid or not self._devices:
            return
        device = self._devices[0]
        udid = device.get("udid")
        if not udid:
            self.toast.emit("Detected device has no UDID - re-plug the iPhone and rescan")
            self.start_btn.setEnabled(True)
            return
        self.toast.emit("Starting extraction...")
        self.start_btn.setEnabled(False)
        api.run_async(
            api.post,
            on_result=self._on_extraction_started,
            on_error=lambda msg: self._on_extraction_start_failed(msg),
            path="/acquisitions/quick-backup",
            params={"case_id": cid, "udid": udid, "full": "true"},
        )

    def _on_extraction_start_failed(self, msg: str) -> None:
        self.toast.emit(f"Failed: {msg}")
        self.start_btn.setEnabled(True)

    def _on_extraction_started(self, result) -> None:
        self._acq_id = (result or {}).get("acquisition_id")
        if not self._acq_id:
            self.toast.emit("Failed - check device connection")
            self.start_btn.setEnabled(True)
            return
        self.progress_block.setVisible(True)
        self.start_btn.setVisible(False)
        self._poll_timer.start()

    def _poll_status(self) -> None:
        if not self._acq_id:
            return
        api.run_async(
            api.get,
            on_result=self._on_status,
            on_error=lambda msg: None,
            path=f"/acquisitions/{self._acq_id}",
        )

    _DONE_STATES = ("complete", "completed", "done", "finished", "success")
    _FAIL_STATES = ("failed", "error", "errored", "cancelled", "canceled")

    def _on_status(self, result) -> None:
        if not result:
            return
        status = (result.get("status") or "running").lower()
        stage = result.get("stage") or ""
        pct = int(result.get("percentage") or 0)
        files = result.get("files_extracted")
        bts = result.get("bytes_extracted")

        self.status_label.setText(f"Status: {status}  ·  {stage}".strip())
        self.progress_bar.setValue(pct)
        parts = []
        if files:
            parts.append(f"{fmt(files)} files")
        if bts:
            parts.append(fmt_bytes(bts))
        self.progress_sub.setText(" · ".join(parts))

        if status in self._DONE_STATES or status in self._FAIL_STATES:
            self._poll_timer.stop()
            if status in self._DONE_STATES:
                self.toast.emit("Extraction complete - parsing evidence...")
                self.status_label.setText("Status: parsing evidence...")
                self.progress_bar.setRange(0, 0)
                api.run_async(
                    api.post,
                    on_result=self._on_parse_complete,
                    on_error=self._on_parse_error,
                    path=f"/analysis/parse/{self._acq_id}",
                )
            else:
                self.toast.emit("Extraction failed")
                self.start_btn.setVisible(True)
                self.start_btn.setEnabled(True)

    def _on_parse_complete(self, result) -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.status_label.setText("Status: complete")
        self.toast.emit("Evidence parsed successfully")
        self.view_evidence_btn.setVisible(True)

    def _on_parse_error(self, msg: str) -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.status_label.setText("Status: complete (parse error)")
        self.toast.emit(f"Parse error: {msg}")
        self.view_evidence_btn.setVisible(True)

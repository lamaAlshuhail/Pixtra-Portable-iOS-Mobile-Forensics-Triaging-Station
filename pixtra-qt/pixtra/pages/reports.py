import webbrowser
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import api, icons
from ..api import API_BASE
from ..format import fmt_time
from ..services import session as session_svc
from ..state import AppState
from ..touch import enable_touch_scroll


class ReportsPage(QWidget):
    toast = pyqtSignal(str)

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state

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
        root = QVBoxLayout(inner)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        gen = QFrame()
        gen.setObjectName("card")
        gl = QVBoxLayout(gen)
        gl.setContentsMargins(14, 12, 14, 12)
        gl.setSpacing(8)

        title = QLabel("Generate Report")
        title.setObjectName("cardTitle")
        gl.addWidget(title)

        lbl = QLabel("Report Title")
        lbl.setObjectName("formLabel")
        gl.addWidget(lbl)
        self.title_input = QLineEdit("Forensic Examination Report")
        self.title_input.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        gl.addWidget(self.title_input)

        lbl2 = QLabel("Examiner Name")
        lbl2.setObjectName("formLabel")
        gl.addWidget(lbl2)
        self.examiner_input = QLineEdit()
        self.examiner_input.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        gl.addWidget(self.examiner_input)

        fmt_lbl = QLabel("Output Format")
        fmt_lbl.setObjectName("formLabel")
        gl.addWidget(fmt_lbl)

        seg = QFrame()
        seg.setObjectName("segGroup")
        seg.setFixedWidth(200)
        sg = QHBoxLayout(seg)
        sg.setContentsMargins(2, 2, 2, 2)
        sg.setSpacing(2)
        self._fmt = "html"
        self._fmt_group = QButtonGroup(self)
        self._fmt_group.setExclusive(True)
        for key, label in [("html", "HTML"), ("pdf", "PDF")]:
            btn = QPushButton(label)
            btn.setObjectName("segBtn")
            btn.setCheckable(True)
            if key == "html":
                btn.setChecked(True)
            btn.clicked.connect(lambda _=False, k=key: setattr(self, "_fmt", k))
            sg.addWidget(btn)
            self._fmt_group.addButton(btn)
        gl.addWidget(seg)

        self.generate_btn = QPushButton("Generate Report")
        self.generate_btn.setObjectName("btnPrimary")
        self.generate_btn.clicked.connect(self._generate)
        gl.addWidget(self.generate_btn, 0, Qt.AlignmentFlag.AlignLeft)

        root.addWidget(gen)

        self.list_card = QFrame()
        self.list_card.setObjectName("card")
        ll = QVBoxLayout(self.list_card)
        ll.setContentsMargins(14, 12, 14, 12)
        ll.setSpacing(6)
        lt = QLabel("Generated Reports")
        lt.setObjectName("cardTitle")
        ll.addWidget(lt)
        self.reports_layout = QVBoxLayout()
        self.reports_layout.setSpacing(4)
        ll.addLayout(self.reports_layout)
        self.list_card.setVisible(False)
        root.addWidget(self.list_card)

        root.addStretch()

        self.scroll.setWidget(inner)
        outer.addWidget(self.scroll)

        state.case_info_changed.connect(self._on_case_info_changed)
        state.case_changed.connect(lambda _: self._load_reports())
        self._on_case_info_changed(state.case_info)

        session_svc.signals().authenticated.connect(self._apply_role_guards)
        session_svc.signals().session_expired.connect(self._apply_role_guards)
        self._apply_role_guards()

    def on_show(self) -> None:
        self._load_reports()

    def _apply_role_guards(self) -> None:
        is_viewer = session_svc.is_viewer()
        self.generate_btn.setVisible(not is_viewer)

    def _on_case_info_changed(self, info: Optional[dict]) -> None:
        if info and info.get("examiner"):
            self.examiner_input.setText(info["examiner"])

    def _generate(self) -> None:
        if not self.state.case_id:
            return
        self.generate_btn.setEnabled(False)
        self.generate_btn.setText("Generating...")
        body = {
            "title": self.title_input.text().strip(),
            "examiner": self.examiner_input.text().strip(),
            "format": self._fmt,
        }
        api.run_async(
            api.post,
            on_result=self._on_generated,
            on_error=lambda msg: self._on_gen_error(msg),
            path=f"/reports/{self.state.case_id}/generate",
            body=body,
        )

    def _on_generated(self, _result) -> None:
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("Generate Report")
        self.toast.emit("Report generated successfully!")
        self._load_reports()

    def _on_gen_error(self, msg: str) -> None:
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("Generate Report")
        self.toast.emit(f"Report failed: {msg}")

    def _load_reports(self) -> None:
        if not self.state.case_id:
            return
        api.run_async(
            api.get,
            on_result=self._on_list_loaded,
            on_error=lambda msg: None,
            path=f"/reports/{self.state.case_id}/list",
        )

    def _on_list_loaded(self, data) -> None:
        while self.reports_layout.count():
            item = self.reports_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        reports = data if isinstance(data, list) else ((data or {}).get("reports") or [])
        if not reports:
            self.list_card.setVisible(False)
            return
        self.list_card.setVisible(True)
        for r in reports:
            self.reports_layout.addWidget(self._row(r))

    def _row(self, r: dict) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background: #FFFFFF; border-bottom: 1px solid #E8E8E2; }"
        )
        row = QHBoxLayout(frame)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(10)

        av = QLabel()
        av.setFixedSize(32, 32)
        av.setAlignment(Qt.AlignmentFlag.AlignCenter)
        av.setStyleSheet("background: #E3F2FD;")
        av.setPixmap(icons.pixmap("file_text", size=18, color="#1565C0"))
        row.addWidget(av)

        mid = QVBoxLayout()
        mid.setSpacing(0)
        fn = QLabel(r.get("filename") or r.get("title") or "Report")
        fn.setObjectName("monoSm")
        fn.setStyleSheet("color: #1C1C1A; font-weight: 600;")
        fn.setWordWrap(True)
        mid.addWidget(fn)
        meta = QLabel(fmt_time(r.get("created_at")) or r.get("format", ""))
        meta.setObjectName("subtle")
        meta.setWordWrap(True)
        mid.addWidget(meta)
        row.addLayout(mid, 1)

        dl = QPushButton("Download")
        dl.setObjectName("btnSm")
        dl.setStyleSheet("background:#EAEAE4; color:#62625F; padding:6px 10px;")
        filename = r.get("filename", "")
        dl.clicked.connect(lambda _, f=filename: self._download(f))
        row.addWidget(dl)

        return frame

    def _download(self, filename: str) -> None:
        if not filename or not self.state.case_id:
            return
        url = f"{API_BASE}/reports/{self.state.case_id}/download/{filename}"
        webbrowser.open(url)

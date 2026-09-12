from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import api
from ..format import fmt_iso8601
from ..services import session as session_svc
from ..theme import MONO_FAMILY, TEXT_MUTED, TEXT_PRIMARY
from ..widgets.list_row import ListRow
from ..widgets.scroll_area import TouchScrollArea


def _build_case_row(case: dict) -> ListRow:
    number_lbl = QLabel(case.get("case_number", ""))
    number_lbl.setStyleSheet(
        f"QLabel {{"
        f"  color: {TEXT_PRIMARY};"
        f"  font-family: {MONO_FAMILY};"
        f"  font-size: 13px;"
        f"  font-weight: 500;"
        f"  background: transparent;"
        f"  border: none;"
        f"}}"
    )

    name = case.get("name") or "(unnamed)"
    examiner = case.get("examiner") or ""
    when = fmt_iso8601(case.get("updated_at") or case.get("created_at"))
    subtitle_text = " · ".join(x for x in (name, examiner, when) if x)
    subtitle_lbl = QLabel(subtitle_text)
    subtitle_lbl.setStyleSheet(
        f"QLabel {{"
        f"  color: {TEXT_MUTED};"
        f"  font-size: 11px;"
        f"  background: transparent;"
        f"  border: none;"
        f"}}"
    )
    subtitle_lbl.setWordWrap(True)

    status = (case.get("status") or "active").lower()
    variant = "active" if status == "active" else "muted"

    return ListRow(
        body_widgets=[number_lbl, subtitle_lbl],
        evidence_band=True,
        badge_text=status.upper(),
        badge_variant=variant,
        payload=case,
    )


class CasesPage(QWidget):

    case_selected = pyqtSignal(str)
    navigate_requested = pyqtSignal(str)
    toast = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._cases: list[dict] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(8, 0, 8, 0)
        title = QLabel("Cases")
        title.setStyleSheet(
            "font-size: 22px; font-weight: 800; background: transparent;"
        )
        header_row.addWidget(title)
        self.count_label = QLabel("0 cases")
        self.count_label.setObjectName("mutedText")
        self.count_label.setStyleSheet(
            "background: transparent; padding-left: 8px;"
        )
        header_row.addWidget(self.count_label)
        header_row.addStretch(1)

        self.create_btn = QPushButton("Create")
        self.create_btn.setObjectName("pillCreate")
        self.create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.create_btn.clicked.connect(
            lambda: self.navigate_requested.emit("new_case")
        )
        header_row.addWidget(self.create_btn)
        root.addLayout(header_row)

        session_svc.signals().authenticated.connect(self._apply_role_guards)
        session_svc.signals().session_expired.connect(self._apply_role_guards)
        self._apply_role_guards()

        self.scroll = TouchScrollArea()

        self.list_host = QWidget()
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(8, 4, 8, 8)
        self.list_layout.setSpacing(10)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.list_host)
        root.addWidget(self.scroll, 1)


    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def refresh(self) -> None:
        api.run_async(
            api.get,
            on_result=self._on_loaded,
            on_error=lambda msg: self.toast.emit(f"Load failed: {msg}"),
            path="/cases",
        )

    def _on_loaded(self, data) -> None:
        if isinstance(data, dict):
            data = data.get("cases", [])
        self._cases = list(data or [])
        self.count_label.setText(f"{len(self._cases)} cases")

        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        if not self._cases:
            empty = QLabel("No cases yet - tap Create to start one.")
            empty.setObjectName("mutedText")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                "background: transparent; padding: 32px 0;"
            )
            self.list_layout.insertWidget(0, empty)
            return

        for case in self._cases:
            row = _build_case_row(case)
            row.clicked.connect(self._open_case)
            self.list_layout.insertWidget(self.list_layout.count() - 1, row)

    def _open_case(self, payload) -> None:
        if isinstance(payload, dict):
            case_id = str(payload.get("id") or "")
            if case_id:
                self.case_selected.emit(case_id)

    def _apply_role_guards(self) -> None:
        self.create_btn.setVisible(not session_svc.is_viewer())

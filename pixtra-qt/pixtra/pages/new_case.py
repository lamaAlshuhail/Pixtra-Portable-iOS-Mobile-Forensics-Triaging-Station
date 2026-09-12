from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .. import api
from ..theme import apply_card_shadow
from ..widgets.drive_picker import DrivePicker


class NewCasePage(QWidget):
    case_selected = pyqtSignal(str)
    navigate_requested = pyqtSignal(str)
    toast = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(12)

        title = QLabel("New Case")
        title.setStyleSheet(
            "font-size: 22px; font-weight: 800; background: transparent;"
        )
        root.addWidget(title)

        card = QFrame()
        card.setObjectName("roundCard")
        apply_card_shadow(card)
        col = QVBoxLayout(card)
        col.setContentsMargins(20, 18, 20, 18)
        col.setSpacing(10)

        col.addWidget(self._label("Case Number"))
        self.input_case_number = QLineEdit()
        self.input_case_number.setObjectName("inputRound")
        self.input_case_number.setPlaceholderText("e.g. CASE-2026-001")
        col.addWidget(self.input_case_number)

        col.addWidget(self._label("Case Name"))
        self.input_name = QLineEdit()
        self.input_name.setObjectName("inputRound")
        self.input_name.setPlaceholderText("Short descriptive title")
        col.addWidget(self.input_name)

        col.addWidget(self._label("Examiner Name"))
        self.input_examiner = QLineEdit()
        self.input_examiner.setObjectName("inputRound")
        self.input_examiner.setPlaceholderText("Your name")
        col.addWidget(self.input_examiner)

        col.addWidget(self._label("External Drive"))
        self.drive_picker = DrivePicker()
        col.addWidget(self.drive_picker)

        col.addWidget(self._label("Notes"))
        self.input_notes = QTextEdit()
        self.input_notes.setObjectName("inputRound")
        self.input_notes.setFixedHeight(80)
        col.addWidget(self.input_notes)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("pillSecondary")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(lambda: self.navigate_requested.emit("cases"))
        actions.addWidget(cancel)

        self.create_btn = QPushButton("Create Case")
        self.create_btn.setObjectName("pillCreate")
        self.create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.create_btn.clicked.connect(self._submit)
        actions.addWidget(self.create_btn)
        col.addLayout(actions)

        root.addWidget(card)
        root.addStretch(1)

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("formLabel")
        return lbl

    def showEvent(self, event):
        super().showEvent(event)
        self.drive_picker.rescan()

    def _submit(self) -> None:
        body = {
            "case_number": self.input_case_number.text().strip(),
            "name": self.input_name.text().strip(),
            "examiner": self.input_examiner.text().strip(),
            "notes": self.input_notes.toPlainText().strip(),
            "storage_root": self.drive_picker.selected_path(),
        }
        if not body["case_number"] or not body["name"] or not body["examiner"]:
            self.toast.emit("Case Number, Name, and Examiner are required")
            return
        if not body["storage_root"]:
            self.toast.emit("Select an external drive for case storage")
            return

        self.create_btn.setEnabled(False)
        api.run_async(
            api.post,
            on_result=self._on_ok,
            on_error=self._on_fail,
            path="/cases",
            body=body,
        )

    def _on_ok(self, result) -> None:
        self.create_btn.setEnabled(True)
        if not result:
            self.toast.emit("Create failed - empty response")
            return
        self.toast.emit(f"Case created: {result.get('case_number', '')}")
        self.input_case_number.clear()
        self.input_name.clear()
        self.input_examiner.clear()
        self.input_notes.clear()
        cid = result.get("id")
        if cid:
            self.case_selected.emit(str(cid))

    def _on_fail(self, msg: str) -> None:
        self.create_btn.setEnabled(True)
        self.toast.emit(f"Create failed: {msg}")

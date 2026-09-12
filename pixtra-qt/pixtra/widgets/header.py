from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from .. import icons
from ..state import AppState


class Header(QWidget):
    close_case_requested = pyqtSignal()

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self.setObjectName("header")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(14, 0, 14, 0)
        outer.setSpacing(8)

        self.title_label = QLabel("Pixtra")
        self.title_label.setObjectName("headerTitle")
        outer.addWidget(self.title_label)
        outer.addStretch()

        self.case_bar = QFrame()
        self.case_bar.setObjectName("headerCaseBar")
        cb_layout = QHBoxLayout(self.case_bar)
        cb_layout.setContentsMargins(10, 2, 2, 2)
        cb_layout.setSpacing(6)

        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(f"color: #3BAF78; font-size: 10px;")
        cb_layout.addWidget(self.status_dot)

        self.case_number_label = QLabel("")
        self.case_number_label.setObjectName("headerCaseNumber")
        cb_layout.addWidget(self.case_number_label)

        self.sep_label = QLabel("·")
        self.sep_label.setStyleSheet("color: #C0C0B8;")
        cb_layout.addWidget(self.sep_label)

        self.user_icon = QLabel()
        self.user_icon.setFixedSize(13, 13)
        self.user_icon.setPixmap(icons.pixmap("user_circle", size=13, color="#62625F"))
        cb_layout.addWidget(self.user_icon)

        self.examiner_label = QLabel("")
        self.examiner_label.setMaximumWidth(90)
        cb_layout.addWidget(self.examiner_label)

        self.close_btn = QPushButton()
        self.close_btn.setObjectName("btnIcon")
        self.close_btn.setIcon(icons.qicon("x", size=14, color="#62625F"))
        self.close_btn.setIconSize(icons.icon_size(14))
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setToolTip("Close case")
        self.close_btn.clicked.connect(self.close_case_requested.emit)
        cb_layout.addWidget(self.close_btn)

        outer.addWidget(self.case_bar)

        self.no_case_bar = QFrame()
        self.no_case_bar.setObjectName("headerNoCase")
        nc_layout = QHBoxLayout(self.no_case_bar)
        nc_layout.setContentsMargins(10, 4, 10, 4)
        nc_layout.setSpacing(6)
        lock_icon = QLabel()
        lock_icon.setFixedSize(12, 12)
        lock_icon.setPixmap(icons.pixmap("lock", size=12, color="#7A7A72"))
        nc_layout.addWidget(lock_icon)
        nc_layout.addWidget(QLabel("No case selected"))
        outer.addWidget(self.no_case_bar)

        state.case_info_changed.connect(self._on_case_info_changed)
        self._on_case_info_changed(state.case_info)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def _on_case_info_changed(self, info: Optional[dict]) -> None:
        if info:
            self.case_bar.setVisible(True)
            self.no_case_bar.setVisible(False)
            self.case_number_label.setText(info.get("case_number", ""))
            self.examiner_label.setText(info.get("examiner") or "Unassigned")
        else:
            self.case_bar.setVisible(False)
            self.no_case_bar.setVisible(True)

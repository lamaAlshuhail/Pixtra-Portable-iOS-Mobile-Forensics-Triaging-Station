from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from .. import icons


class NoCaseSelected(QWidget):
    go_to_cases = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 40, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        card = QFrame()
        card.setObjectName("card")
        card.setFixedWidth(400)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 32, 24, 24)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        icon_label = QLabel()
        icon_label.setFixedSize(40, 40)
        icon_label.setPixmap(icons.pixmap("folder_open", size=40, color="#98988F", stroke=1.25))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignHCenter)

        title = QLabel("No case selected")
        title.setObjectName("mutedText")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        btn = QPushButton("Go to Cases")
        btn.setObjectName("btnPrimary")
        btn.setFixedWidth(160)
        btn.clicked.connect(self.go_to_cases.emit)
        layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)

        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)

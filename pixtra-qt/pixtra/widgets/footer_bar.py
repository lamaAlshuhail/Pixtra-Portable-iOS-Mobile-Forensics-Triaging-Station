from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from .. import icons
from ..theme import FOOTER_TEXT


class FooterBar(QWidget):

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("footerBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 4, 16, 4)
        row.setSpacing(8)

        clock_icon = QLabel()
        clock_icon.setPixmap(icons.pixmap("clock", size=14, color=FOOTER_TEXT))
        row.addWidget(clock_icon)
        self.time_label = QLabel("--:--:--")
        self.time_label.setObjectName("footerText")
        row.addWidget(self.time_label)

        row.addStretch(1)

        cal_icon = QLabel()
        cal_icon.setPixmap(icons.pixmap("calendar", size=14, color=FOOTER_TEXT))
        row.addWidget(cal_icon)
        self.date_label = QLabel("--/--/----")
        self.date_label.setObjectName("footerText")
        row.addWidget(self.date_label)

        self._tick()
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self) -> None:
        now = datetime.now()
        self.time_label.setText(now.strftime("%H:%M:%S"))
        self.date_label.setText(now.strftime("%d/%m/%Y"))

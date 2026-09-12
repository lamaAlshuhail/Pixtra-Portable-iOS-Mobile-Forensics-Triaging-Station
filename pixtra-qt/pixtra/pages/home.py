from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ..services import session as session_svc
from ..widgets.tile import Tile


class HomePage(QWidget):
    navigate_requested = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMaximumHeight(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 0, 40, 0)
        root.setSpacing(0)

        root.addStretch(1)

        tiles_row = QHBoxLayout()
        tiles_row.setSpacing(24)
        tiles_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        mobile = Tile(page_id="cases", icon_name="smartphone", label="Mobile")
        mobile.setMinimumSize(180, 180)
        mobile.tile_clicked.connect(self.navigate_requested.emit)
        tiles_row.addWidget(mobile)

        sim = Tile(
            page_id="cases",
            icon_name="credit_card",
            label="SIM Card",
        )
        sim.setMinimumSize(180, 180)
        sim.tile_clicked.connect(self.navigate_requested.emit)
        tiles_row.addWidget(sim)

        self._users_tile = Tile(
            page_id="users",
            icon_name="users",
            label="Manage\nExaminers",
        )
        self._users_tile.setMinimumSize(180, 180)
        self._users_tile.tile_clicked.connect(self.navigate_requested.emit)
        tiles_row.addWidget(self._users_tile)
        session_svc.signals().authenticated.connect(self._refresh_role_tiles)
        session_svc.signals().session_expired.connect(self._refresh_role_tiles)
        self._refresh_role_tiles()

        root.addLayout(tiles_row)

        root.addStretch(4)

    def _refresh_role_tiles(self) -> None:
        self._users_tile.setVisible(session_svc.is_supervisor())

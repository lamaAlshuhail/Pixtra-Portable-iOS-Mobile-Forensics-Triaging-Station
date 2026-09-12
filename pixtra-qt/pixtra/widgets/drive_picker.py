import glob
import os
import platform
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QPushButton,
    QWidget,
)

from .. import icons


class DrivePicker(QWidget):

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self.combo = QComboBox()
        self.combo.setObjectName("driveCombo")
        self.combo.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(self.combo, 1)

        self.refresh_btn = QPushButton()
        self.refresh_btn.setObjectName("btnIcon")
        self.refresh_btn.setIcon(icons.qicon("refresh", size=16))
        self.refresh_btn.setIconSize(icons.icon_size(16))
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setToolTip("Rescan drives")
        self.refresh_btn.clicked.connect(self.rescan)
        row.addWidget(self.refresh_btn)

        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.setObjectName("btnSm")
        self.browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_btn.clicked.connect(self._browse)
        row.addWidget(self.browse_btn)

        self.rescan()

    def _detect_mounts(self) -> list[str]:
        if platform.system() != "Linux":
            return []
        mounts: list[str] = []
        for pattern in ("/media/*/*", "/run/media/*/*"):
            for path in glob.glob(pattern):
                if os.path.isdir(path):
                    mounts.append(path)
        return sorted(set(mounts))

    def rescan(self) -> None:
        current = self.selected_path()
        self.combo.clear()
        self.combo.addItem("(no drive selected)", userData=None)
        for path in self._detect_mounts():
            self.combo.addItem(path, userData=path)
        if current:
            idx = self.combo.findData(current)
            if idx >= 0:
                self.combo.setCurrentIndex(idx)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select storage drive")
        if not path:
            return
        idx = self.combo.findData(path)
        if idx < 0:
            self.combo.addItem(path, userData=path)
            idx = self.combo.count() - 1
        self.combo.setCurrentIndex(idx)

    def selected_path(self) -> Optional[str]:
        return self.combo.currentData()

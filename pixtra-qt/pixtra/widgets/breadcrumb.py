from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from ..theme import TEXT_PRIMARY, TEXT_SECONDARY, TYPE_SM


_SEPARATOR = "›"


class Breadcrumb(QWidget):

    navigate_requested = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("breadcrumb")
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._layout.addStretch(1)
        self._items: list[tuple[str, str]] = []
        self.setVisible(False)

    def set_items(self, items: list[tuple[str, str]]) -> None:
        self._items = list(items or [])
        self._rebuild()

    def _rebuild(self) -> None:
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        if not self._items:
            self.setVisible(False)
            return
        self.setVisible(True)

        for idx, (label, page_id) in enumerate(self._items):
            is_last = idx == len(self._items) - 1
            if is_last or not page_id:
                lbl = QLabel(label)
                if is_last:
                    lbl.setStyleSheet(
                        f"QLabel {{"
                        f"  color: {TEXT_PRIMARY};"
                        f"  font-size: {TYPE_SM}px;"
                        f"  font-weight: 700;"
                        f"  background: transparent; border: none;"
                        f"  padding: 0;"
                        f"}}"
                    )
                else:
                    lbl.setStyleSheet(
                        f"QLabel {{"
                        f"  color: {TEXT_SECONDARY};"
                        f"  font-size: {TYPE_SM}px;"
                        f"  background: transparent; border: none;"
                        f"  padding: 0;"
                        f"}}"
                    )
                self._layout.insertWidget(self._layout.count() - 1, lbl)
            else:
                btn = QPushButton(label)
                btn.setObjectName("breadcrumbLink")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setFlat(True)
                btn.setStyleSheet(
                    f"QPushButton#breadcrumbLink {{"
                    f"  background: transparent;"
                    f"  color: {TEXT_SECONDARY};"
                    f"  font-size: {TYPE_SM}px;"
                    f"  border: none;"
                    f"  padding: 0;"
                    f"  text-align: left;"
                    f"}}"
                    f"QPushButton#breadcrumbLink:hover {{"
                    f"  color: {TEXT_PRIMARY};"
                    f"  text-decoration: underline;"
                    f"}}"
                )
                btn.clicked.connect(
                    lambda _checked, pid=page_id: self.navigate_requested.emit(pid)
                )
                self._layout.insertWidget(self._layout.count() - 1, btn)

            if not is_last:
                sep = QLabel(_SEPARATOR)
                sep.setStyleSheet(
                    f"QLabel {{"
                    f"  color: {TEXT_SECONDARY};"
                    f"  font-size: {TYPE_SM}px;"
                    f"  background: transparent; border: none;"
                    f"  padding: 0;"
                    f"}}"
                )
                self._layout.insertWidget(self._layout.count() - 1, sep)

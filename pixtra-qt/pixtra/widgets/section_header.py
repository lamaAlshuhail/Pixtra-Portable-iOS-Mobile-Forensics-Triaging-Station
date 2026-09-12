from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QLabel, QWidget

from ..theme import TEXT_SECONDARY, TYPE_XS


class SectionHeader(QLabel):

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text.upper(), parent)
        self.setObjectName("sectionHeader")
        self.setStyleSheet(
            f"QLabel#sectionHeader {{"
            f"  color: {TEXT_SECONDARY};"
            f"  font-size: {TYPE_XS}px;"
            f"  font-weight: 700;"
            f"  letter-spacing: 1px;"
            f"  background: transparent;"
            f"  border: none;"
            f"  padding: 0;"
            f"}}"
        )

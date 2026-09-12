from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPalette
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import icons
from ..format import fmt
from ..state import AppState


@dataclass
class NavEntry:
    page_id: str
    icon: str
    label: str
    requires_case: bool = False
    count_key: Optional[str] = None


@dataclass
class NavSection:
    label: str


NAV_ITEMS = [
    NavEntry("dashboard", "layout_dashboard", "Dashboard", requires_case=True),
    NavEntry("cases", "folder_open", "Cases"),
    NavEntry("devices", "smartphone", "Devices"),
    NavEntry("acquire", "download", "Acquire", requires_case=True),
    NavSection("Evidence"),
    NavEntry("messages", "message_square", "Messages", requires_case=True, count_key="messages"),
    NavEntry("contacts", "users", "Contacts", requires_case=True, count_key="contacts"),
    NavEntry("calls", "phone", "Calls", requires_case=True, count_key="calls"),
    NavEntry("web", "globe", "Web History", requires_case=True, count_key="web_history"),
    NavSection("Analysis"),
    NavEntry("timeline", "clock", "Timeline", requires_case=True),
    NavEntry("graph", "share2", "Entity Graph", requires_case=True),
    NavEntry("custody", "shield_check", "Chain of Custody", requires_case=True),
    NavEntry("reports", "file_text", "Reports", requires_case=True),
    NavSection("Advanced"),
    NavEntry("checkm8", "zap", "checkm8"),
]

_SIDEBAR_BG = QColor("#0D2818")


class SidebarItem(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, entry: NavEntry, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.entry = entry
        self._disabled = False

        self.setObjectName("sidebarItem")
        self.setProperty("active", False)
        self.setProperty("disabled", False)
        self.setFixedHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 12, 0)
        layout.setSpacing(8)

        self.text_label = QLabel(entry.label)
        self.text_label.setObjectName("sidebarItemText")
        layout.addWidget(self.text_label, 1)

        self.trailing_label = QLabel()
        self.trailing_label.setObjectName("sidebarBadge")
        self.trailing_label.setVisible(False)
        layout.addWidget(self.trailing_label)

        self.lock_label = QLabel()
        self.lock_label.setFixedSize(12, 12)
        self.lock_label.setVisible(False)
        layout.addWidget(self.lock_label)

    def set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self._repolish()

    def set_disabled(self, disabled: bool) -> None:
        self._disabled = disabled
        self.setProperty("disabled", disabled)
        self.setCursor(Qt.CursorShape.ForbiddenCursor if disabled else Qt.CursorShape.PointingHandCursor)
        if disabled:
            self.lock_label.setPixmap(icons.pixmap("lock", size=12, color="#FFFFFF66"))
            self.lock_label.setVisible(True)
            self.trailing_label.setVisible(False)
        else:
            self.lock_label.setVisible(False)
        self._repolish()

    def set_count(self, count: int) -> None:
        if self._disabled or not count:
            self.trailing_label.setVisible(False)
            return
        self.trailing_label.setText(fmt(count))
        self.trailing_label.setVisible(True)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if not self._disabled and e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.entry.page_id)
        super().mousePressEvent(e)

    def _repolish(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)


class Sidebar(QWidget):
    navigate_requested = pyqtSignal(str)

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self.setObjectName("sidebar")
        self.setFixedWidth(160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        logo = QLabel("Pixtra")
        logo.setObjectName("sidebarLogo")
        logo.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(logo)

        self._items: dict[str, SidebarItem] = {}
        for entry in NAV_ITEMS:
            if isinstance(entry, NavSection):
                div = QFrame()
                div.setObjectName("sidebarDivider")
                layout.addWidget(div)
                continue
            item = SidebarItem(entry)
            item.clicked.connect(self._on_item_clicked)
            self._items[entry.page_id] = item
            layout.addWidget(item)

        layout.addStretch()


        state.case_changed.connect(self._on_case_changed)
        state.evidence_changed.connect(self._on_evidence_changed)
        self._on_case_changed(state.case_id)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), _SIDEBAR_BG)
        painter.end()
        super().paintEvent(event)

    def set_active(self, page_id: str) -> None:
        for pid, item in self._items.items():
            item.set_active(pid == page_id)

    def _on_item_clicked(self, page_id: str) -> None:
        self.navigate_requested.emit(page_id)

    def _on_case_changed(self, case_id: Optional[str]) -> None:
        for entry_id, item in self._items.items():
            entry = next(e for e in NAV_ITEMS if isinstance(e, NavEntry) and e.page_id == entry_id)
            disabled = entry.requires_case and not case_id
            item.set_disabled(disabled)

    def _on_evidence_changed(self, _: Optional[dict]) -> None:
        for entry_id, item in self._items.items():
            entry = next(e for e in NAV_ITEMS if isinstance(e, NavEntry) and e.page_id == entry_id)
            if entry.count_key:
                item.set_count(self.state.count(entry.count_key))

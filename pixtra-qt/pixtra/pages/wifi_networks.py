from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import api, icons
from ..format import fmt_time
from ..state import AppState
from ..touch import enable_touch_scroll


_HIDDEN = "••••••••"


class WifiNetworksPage(QWidget):
    COLUMNS = ("SSID", "Security", "Password", "Last connected")

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._rows: list[dict] = []
        self._revealed: set[int] = set()

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        title_row = QHBoxLayout()
        title = QLabel("Wi-Fi Networks")
        title.setStyleSheet(
            "font-size: 22px; font-weight: 800; background: transparent;"
        )
        title_row.addWidget(title)
        self.count_label = QLabel("0 networks")
        self.count_label.setObjectName("mutedText")
        self.count_label.setStyleSheet("background: transparent; padding-left: 8px;")
        title_row.addWidget(self.count_label)
        title_row.addStretch(1)
        self.reveal_all_btn = QPushButton("Reveal all")
        self.reveal_all_btn.setObjectName("btnSm")
        self.reveal_all_btn.setIcon(icons.qicon("eye", size=14))
        self.reveal_all_btn.setIconSize(icons.icon_size(14))
        self.reveal_all_btn.setCheckable(True)
        self.reveal_all_btn.toggled.connect(self._toggle_reveal_all)
        title_row.addWidget(self.reveal_all_btn)
        root.addLayout(title_row)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(list(self.COLUMNS))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        enable_touch_scroll(self.table)
        self.table.cellClicked.connect(self._on_cell_clicked)
        root.addWidget(self.table, 1)

        self.empty_lbl = QLabel(
            "No Wi-Fi networks parsed yet. Awaiting Wi-Fi parser implementation."
        )
        self.empty_lbl.setObjectName("mutedText")
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_lbl.setStyleSheet("background: transparent; padding: 16px;")
        root.addWidget(self.empty_lbl)

        state.case_changed.connect(lambda _: self.refresh())

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        if not self.state.case_id:
            self._populate([])
            return
        api.run_async(
            api.get,
            on_result=self._on_loaded,
            on_error=lambda msg: self._populate([]),
            path=f"/analysis/evidence/{self.state.case_id}/wifi",
        )

    def _on_loaded(self, data) -> None:
        rows = api.coerce_list(data, "networks", "items")
        self._populate(rows)

    def _populate(self, rows: list[dict]) -> None:
        self._rows = rows
        self._revealed.clear()
        self.count_label.setText(f"{len(rows)} networks")
        self.empty_lbl.setVisible(not rows)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self._set_cell(r, 0, row.get("ssid", ""))
            self._set_cell(r, 1, row.get("security", ""))
            self._set_cell(r, 2, _HIDDEN)
            self._set_cell(r, 3, fmt_time(row.get("last_connected")))

    def _set_cell(self, r: int, c: int, text: str) -> None:
        item = QTableWidgetItem(str(text))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(r, c, item)

    def _on_cell_clicked(self, row: int, col: int) -> None:
        if col != 2 or row >= len(self._rows):
            return
        if row in self._revealed:
            self._revealed.discard(row)
            self._set_cell(row, 2, _HIDDEN)
        else:
            self._revealed.add(row)
            self._set_cell(row, 2, self._rows[row].get("password", ""))

    def _toggle_reveal_all(self, checked: bool) -> None:
        for r, row in enumerate(self._rows):
            if checked:
                self._revealed.add(r)
                self._set_cell(r, 2, row.get("password", ""))
            else:
                self._revealed.discard(r)
                self._set_cell(r, 2, _HIDDEN)

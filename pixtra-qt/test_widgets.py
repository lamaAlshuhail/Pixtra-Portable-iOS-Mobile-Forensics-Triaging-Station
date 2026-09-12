import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel
)

from pixtra.widgets.section_header import SectionHeader
from pixtra.widgets.breadcrumb import Breadcrumb
from pixtra.widgets.list_row import ListRow
from pixtra.widgets.empty_state import EmptyState
from pixtra.theme import BG_APP, QSS

app = QApplication(sys.argv)
app.setStyleSheet(QSS)

win = QMainWindow()
win.setStyleSheet(f"background-color: {BG_APP};")
win.resize(800, 600)
win.setWindowTitle("Widget preview")

central = QWidget()
layout = QVBoxLayout(central)
layout.setContentsMargins(16, 16, 16, 16)
layout.setSpacing(16)

bc = Breadcrumb()
bc.set_items([("Cases", "cases"), ("iPhone 13", "dashboard"), ("SIM Extraction", "")])
layout.addWidget(bc)

layout.addWidget(SectionHeader("EVIDENCE"))

row_body = QLabel("Test PLMN · IMSI 001010123456789")
row = ListRow(
    body_widgets=[row_body],
    evidence_band=True,
    badge_text="1",
    payload={"id": "test"},
)
layout.addWidget(row)

layout.addWidget(SectionHeader("WITH NO DATA"))
empty = EmptyState(
    icon_name="inbox",
    title="No SIM extractions yet",
    subtitle="Tap Scan New SIM to begin",
    action_label="+ Scan New SIM",
)
layout.addWidget(empty)

layout.addStretch()
win.setCentralWidget(central)
win.show()

sys.exit(app.exec())

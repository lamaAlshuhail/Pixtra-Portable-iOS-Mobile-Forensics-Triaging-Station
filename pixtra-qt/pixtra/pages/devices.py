from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import api, icons
from ..touch import enable_touch_scroll


def _make_device_card(d: dict) -> QFrame:
    is_ios = (d.get("platform") or "").lower() == "ios"
    tint = "#1B5E3B" if is_ios else "#1565C0"

    card = QFrame()
    card.setObjectName("card")
    card.setStyleSheet(f"QFrame#card {{ border-left: 3px solid {tint}; }}")

    row = QHBoxLayout(card)
    row.setContentsMargins(14, 12, 14, 12)
    row.setSpacing(14)

    icon_box = QFrame()
    icon_box.setFixedSize(40, 40)
    icon_box.setStyleSheet(
        "background: #FAFAF8; border: 1px solid #E8E8E2;"
    )
    ib_layout = QVBoxLayout(icon_box)
    ib_layout.setContentsMargins(0, 0, 0, 0)
    ib_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    icon_label = QLabel()
    icon_label.setPixmap(icons.pixmap("smartphone", size=24, color=tint))
    ib_layout.addWidget(icon_label)
    row.addWidget(icon_box)

    body = QVBoxLayout()
    body.setSpacing(2)
    name = QLabel(d.get("model_name") or d.get("product_type") or "Device")
    name.setStyleSheet("font-size: 14px; font-weight: 700; background: transparent;")
    body.addWidget(name)
    meta = QLabel(
        f"{(d.get('platform') or '').upper()} · {d.get('os_version', '')} · {d.get('chipset', '')}"
    )
    meta.setObjectName("monoSm")
    body.addWidget(meta)
    serial = QLabel(f"Serial {d.get('serial', '')}")
    serial.setObjectName("monoSm")
    body.addWidget(serial)
    if d.get("recommended_method"):
        rec = QLabel(f"Recommended: {d['recommended_method']}")
        rec.setStyleSheet(
            "font-size: 11px; font-weight: 600; color: #1B5E3B; background: transparent;"
        )
        body.addWidget(rec)
    row.addLayout(body, 1)

    caps_col = QVBoxLayout()
    caps_col.setSpacing(3)
    caps_col.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
    for cap in (d.get("capabilities") or [])[:4]:
        tag = QLabel(cap)
        tag.setObjectName("badgeGreen")
        tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caps_col.addWidget(tag)
    row.addLayout(caps_col)

    return card


class DevicesPage(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        toolbar = QHBoxLayout()
        toolbar.addStretch()
        scan_btn = QPushButton("  Scan")
        scan_btn.setObjectName("btnPrimary")
        scan_btn.setIcon(icons.qicon("search", size=14, color="#FFFFFF"))
        scan_btn.setIconSize(icons.icon_size(14))
        scan_btn.clicked.connect(self.scan)
        toolbar.addWidget(scan_btn)
        root.addLayout(toolbar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setObjectName("contentArea")
        enable_touch_scroll(self.scroll)
        self.inner = QWidget()
        self.inner_layout = QVBoxLayout(self.inner)
        self.inner_layout.setContentsMargins(0, 0, 0, 0)
        self.inner_layout.setSpacing(8)
        self.inner_layout.addStretch()
        self.scroll.setWidget(self.inner)
        root.addWidget(self.scroll, 1)

        self._show_loading()

    def showEvent(self, event):
        super().showEvent(event)
        self.scan()

    def scan(self) -> None:
        self._show_loading()
        api.run_async(
            api.get,
            on_result=self._on_scan_result,
            on_error=lambda msg: self._show_error(msg),
            path="/devices/detect",
        )

    def _clear(self) -> None:
        while self.inner_layout.count():
            item = self.inner_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _show_loading(self) -> None:
        self._clear()
        msg = QLabel("Scanning USB devices...")
        msg.setObjectName("mutedText")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inner_layout.addWidget(msg)
        self.inner_layout.addStretch()

    def _show_error(self, msg: str) -> None:
        self._clear()
        err = QLabel(f"Scan failed: {msg}")
        err.setObjectName("mutedText")
        err.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inner_layout.addWidget(err)
        self.inner_layout.addStretch()

    def _on_scan_result(self, result) -> None:
        self._clear()
        devices = result if isinstance(result, list) else (result or {}).get("devices", [])
        if not devices:
            empty = QFrame()
            empty.setObjectName("card")
            el = QVBoxLayout(empty)
            el.setContentsMargins(20, 28, 20, 28)
            el.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon = QLabel()
            icon.setPixmap(icons.pixmap("smartphone", size=48, color="#98988F", stroke=1.25))
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            el.addWidget(icon)
            title = QLabel("No devices detected")
            title.setStyleSheet("font-size: 14px; font-weight: 600; background: transparent;")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            el.addWidget(title)
            self.inner_layout.addWidget(empty)
        else:
            for d in devices:
                self.inner_layout.addWidget(_make_device_card(d))
        self.inner_layout.addStretch()

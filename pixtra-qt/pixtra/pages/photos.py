from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import api, icons
from ..format import fmt, fmt_bytes, fmt_time
from ..state import AppState
from ..theme import GREEN_700, RADIUS_CARD, apply_card_shadow
from ..touch import enable_touch_scroll


class _ThumbTile(QLabel):

    clicked = pyqtSignal(dict)

    def __init__(self, photo: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._photo = photo
        self.setObjectName("photoThumb")
        self.setFixedSize(200, 200)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QLabel#photoThumb {{ background: #EAEAE4; "
            f"border-radius: {RADIUS_CARD}px; }}"
        )
        self.setPixmap(icons.pixmap("image", size=48, color="#98988F", stroke=1.5))

    def set_image_bytes(self, data: bytes) -> None:
        pix = QPixmap()
        if pix.loadFromData(data):
            scaled = pix.scaled(
                200, 200,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setPixmap(scaled)

    def set_failed(self) -> None:
        self.setPixmap(icons.pixmap("alert_triangle", size=40, color="#C62828"))

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._photo)
        super().mousePressEvent(e)


class PhotosPage(QWidget):
    navigate_requested = pyqtSignal(str)

    PAGE_SIZE = 50
    GRID_COLS = 2

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._photos: list[dict] = []
        self._total = 0
        self._offset = 0
        self._with_gps_filter: Optional[bool] = None
        self._workers: list = []
        self._loading_more = False

        self.stack = QStackedWidget(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.stack)

        self.stack.addWidget(self._build_grid_view())
        self.stack.addWidget(self._build_viewer_view())

        state.case_changed.connect(lambda _: self.refresh())

    def on_show(self) -> None:
        self.refresh()

    def _build_grid_view(self) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(8, 8, 8, 8)
        col.setSpacing(8)

        title_row = QHBoxLayout()
        title = QLabel("Photos")
        title.setStyleSheet(
            "font-size: 22px; font-weight: 800; background: transparent;"
        )
        title_row.addWidget(title)
        self.count_label = QLabel("0 photos")
        self.count_label.setObjectName("mutedText")
        self.count_label.setStyleSheet("background: transparent; padding-left: 8px;")
        title_row.addWidget(self.count_label)
        title_row.addStretch(1)
        col.addLayout(title_row)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)
        for label, value in (("All", None), ("With GPS", True)):
            btn = QPushButton(label)
            btn.setObjectName("chipFilter")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if value is None:
                btn.setChecked(True)
            btn.clicked.connect(lambda _checked, v=value: self._set_filter(v))
            self._chip_group.addButton(btn)
            chips.addWidget(btn)
        by_app = QPushButton("By app")
        by_app.setObjectName("chipFilter")
        by_app.setEnabled(False)
        by_app.setToolTip("Awaiting EXIFParser source_app extension")
        chips.addWidget(by_app)
        chips.addStretch(1)
        col.addLayout(chips)

        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.grid_scroll.setObjectName("contentArea")
        enable_touch_scroll(self.grid_scroll)
        self.grid_host = QWidget()
        self.grid_layout = QGridLayout(self.grid_host)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.grid_scroll.setWidget(self.grid_host)
        col.addWidget(self.grid_scroll, 1)

        self.grid_scroll.verticalScrollBar().valueChanged.connect(
            self._on_scrolled
        )

        return page

    def _build_viewer_view(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.viewer_scroll = QScrollArea()
        self.viewer_scroll.setWidgetResizable(True)
        self.viewer_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.viewer_scroll.setObjectName("contentArea")
        self.viewer_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        enable_touch_scroll(self.viewer_scroll)

        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(8, 8, 8, 8)
        col.setSpacing(6)

        back_btn = QPushButton("  Back")
        back_btn.setObjectName("btnGhost")
        back_btn.setIcon(icons.qicon("chevron_left", size=14, color="#62625F"))
        back_btn.setIconSize(icons.icon_size(14))
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        col.addWidget(back_btn, 0, Qt.AlignmentFlag.AlignLeft)

        self.viewer_title = QLabel("")
        self.viewer_title.setStyleSheet(
            "font-size: 14px; font-weight: 700; background: transparent;"
        )
        self.viewer_title.setWordWrap(True)
        col.addWidget(self.viewer_title)

        body = QHBoxLayout()
        body.setSpacing(12)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet(
            "background: #1C1C1A; border-radius: 8px;"
        )
        self.preview_label.setMinimumHeight(240)
        body.addWidget(self.preview_label, 1)

        exif_frame = QFrame()
        exif_frame.setObjectName("roundCard")
        apply_card_shadow(exif_frame)
        exif_col = QVBoxLayout(exif_frame)
        exif_col.setContentsMargins(14, 12, 14, 12)
        exif_col.setSpacing(6)

        exif_title = QLabel("EXIF")
        exif_title.setStyleSheet(
            f"color: {GREEN_700}; font-size: 12px; font-weight: 700; "
            f"letter-spacing: 0.5px; background: transparent;"
        )
        exif_col.addWidget(exif_title)

        self.exif_timestamp = self._exif_row(exif_col, "Taken")
        self.exif_gps = self._exif_row(exif_col, "GPS")
        self.exif_size = self._exif_row(exif_col, "Size")
        self.exif_filename = self._exif_row(exif_col, "Filename")
        self.exif_camera = self._exif_row(exif_col, "Camera")
        self.exif_app = self._exif_row(exif_col, "Source app")
        exif_col.addStretch(1)
        exif_frame.setMaximumWidth(220)
        body.addWidget(exif_frame)
        col.addLayout(body, 1)

        self.viewer_scroll.setWidget(inner)
        outer.addWidget(self.viewer_scroll)
        return page

    def _exif_row(self, parent_layout: QVBoxLayout, label: str) -> QLabel:
        lbl = QLabel(label)
        lbl.setObjectName("formLabel")
        parent_layout.addWidget(lbl)
        value = QLabel(" - ")
        value.setObjectName("monoSm")
        value.setWordWrap(True)
        parent_layout.addWidget(value)
        return value

    def refresh(self) -> None:
        if not self.state.case_id:
            return
        self._photos = []
        self._offset = 0
        self._total = 0
        self._workers = []
        self._loading_more = False
        self._clear_grid()
        self._fetch_page()

    def _set_filter(self, with_gps: Optional[bool]) -> None:
        self._with_gps_filter = with_gps
        self.refresh()

    def _fetch_page(self) -> None:
        params: dict = {"limit": self.PAGE_SIZE, "offset": self._offset}
        if self._with_gps_filter is True:
            params["with_gps"] = "true"
        elif self._with_gps_filter is False:
            params["with_gps"] = "false"
        api.run_async(
            api.get,
            on_result=self._on_page,
            on_error=lambda _msg: None,
            path=f"/analysis/evidence/{self.state.case_id}/photos",
            params=params,
        )

    def _on_page(self, data) -> None:
        if isinstance(data, dict):
            self._total = int(data.get("total") or 0)
        page = api.coerce_list(data, "photos", "items")
        self._photos.extend(page)
        loaded = len(self._photos)
        if loaded < self._total:
            self.count_label.setText(f"{fmt(loaded)} of {fmt(self._total)} photos")
        else:
            self.count_label.setText(f"{fmt(self._total)} photos")
        self._append_thumbs(page)

    def _load_more(self) -> None:
        self._offset += self.PAGE_SIZE
        api.run_async(
            api.get,
            on_result=self._on_more,
            on_error=lambda _msg: self._on_more(None),
            path=f"/analysis/evidence/{self.state.case_id}/photos",
            params={"limit": self.PAGE_SIZE, "offset": self._offset},
        )

    def _on_more(self, data) -> None:
        self._loading_more = False
        self._on_page(data)

    def _on_scrolled(self, value: int) -> None:
        if self._loading_more:
            return
        sb = self.grid_scroll.verticalScrollBar()
        max_val = sb.maximum()
        if max_val <= 0:
            return
        if value < max_val - 200:
            return
        if len(self._photos) >= self._total:
            return
        self._loading_more = True
        self._load_more()

    def _append_thumbs(self, photos: list[dict]) -> None:
        existing = self.grid_layout.count()
        for i, photo in enumerate(photos):
            tile = _ThumbTile(photo)
            tile.clicked.connect(self._open_viewer)
            r, c = divmod(existing + i, self.GRID_COLS)
            self.grid_layout.addWidget(tile, r, c, Qt.AlignmentFlag.AlignCenter)
            self._spawn_thumb_worker(tile, photo)

    def _spawn_thumb_worker(self, tile: _ThumbTile, photo: dict) -> None:
        url = photo.get("thumbnail_url")
        if not url:
            return
        worker = api.run_async(
            api.get_bytes,
            on_result=lambda data, t=tile: t.set_image_bytes(data),
            on_error=lambda _msg, t=tile: t.set_failed(),
            path=url,
        )
        self._workers.append(worker)

    def _clear_grid(self) -> None:
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _open_viewer(self, photo: dict) -> None:
        self.viewer_title.setText(photo.get("filename") or "(no name)")
        self.preview_label.setText("Loading…")
        self.preview_label.setPixmap(QPixmap())
        self.exif_timestamp.setText(fmt_time(photo.get("timestamp")) or " - ")
        gps_lat = photo.get("gps_lat")
        gps_lon = photo.get("gps_lon")
        if gps_lat is not None and gps_lon is not None:
            self.exif_gps.setText(f"{gps_lat:.5f}, {gps_lon:.5f}")
        else:
            self.exif_gps.setText(" - ")
        size_b = photo.get("size_bytes")
        self.exif_size.setText(fmt_bytes(size_b) if size_b else " - ")
        self.exif_filename.setText(photo.get("filename") or " - ")
        cam_make = photo.get("camera_make")
        cam_model = photo.get("camera_model")
        if cam_make or cam_model:
            self.exif_camera.setText(" ".join(x for x in (cam_make, cam_model) if x))
        else:
            self.exif_camera.setText("Awaiting parser")
        self.exif_app.setText(photo.get("source_app") or "Awaiting parser")

        self.stack.setCurrentIndex(1)

        url = photo.get("preview_url")
        if not url:
            self.preview_label.setText("No preview")
            return
        worker = api.run_async(
            api.get_bytes,
            on_result=self._set_preview_bytes,
            on_error=lambda _msg: self.preview_label.setText("Failed to load"),
            path=url,
        )
        self._workers.append(worker)

    def _set_preview_bytes(self, data: bytes) -> None:
        pix = QPixmap()
        if not pix.loadFromData(data):
            self.preview_label.setText("Decode failed")
            return
        target = self.preview_label.size()
        self.preview_label.setPixmap(
            pix.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

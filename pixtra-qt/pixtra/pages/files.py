from __future__ import annotations

import os
from typing import Optional
from urllib.parse import quote as urlquote

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .. import api, icons
from ..format import fmt, fmt_bytes
from ..state import AppState
from ..theme import GREEN_700, RADIUS_CARD, apply_card_shadow
from ..touch import enable_touch_scroll


_CHIPS: list[tuple[str, Optional[str]]] = [
    ("All", None),
    ("Documents", "document"),
    ("Photos", "image"),
    ("Videos", "video"),
    ("Audio", "audio"),
]

_TYPE_ICONS = {
    "document": "file_text",
    "image": "image",
    "video": "video",
    "audio": "music",
    "other": "file_text",
}

_PREVIEWABLE_TEXT_EXT = {".txt", ".csv", ".log", ".md", ".json", ".xml"}
_TXT_PREVIEW_MAX_LINES = 500


def _infer_source_app(rel_path: str) -> str:
    if not rel_path:
        return ""
    parts = rel_path.replace("\\", "/").split("/")
    if not parts:
        return ""
    domain = parts[0]
    if domain == "AppDomainGroup-group.net.whatsapp.WhatsApp.shared":
        return "WhatsApp"
    if domain == "CameraRollDomain":
        return "Camera Roll"
    if domain.startswith("AppDomain-"):
        bundle = domain[len("AppDomain-"):]
        last = bundle.split(".")[-1] if bundle else ""
        return last[:1].upper() + last[1:] if last else domain
    if domain.startswith("AppDomainGroup-"):
        bundle = domain[len("AppDomainGroup-"):]
        segs = [s for s in bundle.split(".") if s and s.lower() != "shared"]
        if segs:
            tail = segs[-1]
            return tail[:1].upper() + tail[1:]
        return domain
    if domain == "HomeDomain":
        if len(parts) >= 4 and parts[1] == "Library" and parts[2] == "Mobile Documents":
            return f"iCloud Drive: {parts[3]}"
        return "Home"
    return domain


class _FileRow(QFrame):

    clicked = pyqtSignal(dict)

    def __init__(self, file: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._file = file
        self.setObjectName("caseCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(12)

        ftype = (file.get("type") or "other").lower()
        icon_name = _TYPE_ICONS.get(ftype, "file_text")
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(32, 32)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setPixmap(icons.pixmap(icon_name, size=20, color=GREEN_700))
        icon_lbl.setStyleSheet("background: transparent;")
        row.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name = QLabel(file.get("name") or "(no name)")
        name.setStyleSheet(
            "font-size: 13px; font-weight: 600; background: transparent;"
        )
        name.setWordWrap(True)
        name.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        name.setMinimumHeight(0)
        text_col.addWidget(name)

        sub_text = _infer_source_app(file.get("path") or "")
        if sub_text:
            sub = QLabel(sub_text)
            sub.setObjectName("subtle")
            sub.setWordWrap(True)
            sub.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
            )
            sub.setMinimumHeight(0)
            text_col.addWidget(sub)
        row.addLayout(text_col, 1)

        size_lbl = QLabel(fmt_bytes(file.get("size_bytes") or 0))
        size_lbl.setObjectName("monoSm")
        size_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        size_lbl.setFixedWidth(80)
        size_lbl.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
        )
        row.addWidget(size_lbl)

        apply_card_shadow(self)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._file)
        super().mousePressEvent(e)


class FilesPage(QWidget):
    navigate_requested = pyqtSignal(str)
    toast = pyqtSignal(str)

    PAGE_SIZE = 100

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._all_files: list[dict] = []
        self._filtered_files: list[dict] = []
        self._shown_count = 0
        self._file_type: Optional[str] = None
        self._search: str = ""
        self._workers: list = []

        self.stack = QStackedWidget(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.stack)

        self.stack.addWidget(self._build_browser_view())
        self.stack.addWidget(self._build_preview_view())

        state.case_changed.connect(lambda _: self.refresh())

    def on_show(self) -> None:
        self.refresh()

    def _build_browser_view(self) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(8, 8, 8, 8)
        col.setSpacing(8)

        title_row = QHBoxLayout()
        title = QLabel("Files")
        title.setStyleSheet(
            "font-size: 22px; font-weight: 800; background: transparent;"
        )
        title_row.addWidget(title)
        self.count_label = QLabel("0 files")
        self.count_label.setObjectName("mutedText")
        self.count_label.setStyleSheet(
            "background: transparent; padding-left: 8px;"
        )
        title_row.addWidget(self.count_label)
        title_row.addStretch(1)
        col.addLayout(title_row)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)
        for label, value in _CHIPS:
            btn = QPushButton(label)
            btn.setObjectName("chipFilter")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if value is None:
                btn.setChecked(True)
            btn.clicked.connect(lambda _checked, v=value: self._set_file_type(v))
            self._chip_group.addButton(btn)
            chips.addWidget(btn)
        chips.addStretch(1)
        col.addLayout(chips)

        search_row = QFrame()
        search_row.setStyleSheet(
            "background: #FFFFFF; border: 1px solid #C8C8C0;"
        )
        search_row.setFixedHeight(40)
        sl = QHBoxLayout(search_row)
        sl.setContentsMargins(12, 0, 12, 0)
        sl.setSpacing(8)
        sicon = QLabel()
        sicon.setPixmap(icons.pixmap("search", size=14, color="#7A7A72"))
        sl.addWidget(sicon)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search filename…")
        self.search_input.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.search_input.setStyleSheet(
            "border: none; background: transparent; font-size: 13px;"
        )
        self.search_input.textChanged.connect(self._on_search_changed)
        sl.addWidget(self.search_input, 1)
        col.addWidget(search_row)

        self.list_scroll = QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.list_scroll.setObjectName("contentArea")
        self.list_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        enable_touch_scroll(self.list_scroll)
        self.list_host = QWidget()
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch(1)
        self.list_scroll.setWidget(self.list_host)
        col.addWidget(self.list_scroll, 1)

        def _sync_host_width() -> None:
            self.list_host.setMaximumWidth(self.list_scroll.viewport().width())

        original_resize = self.list_scroll.resizeEvent

        def _patched_resize(event):
            original_resize(event)
            _sync_host_width()

        self.list_scroll.resizeEvent = _patched_resize
        _sync_host_width()

        self.list_scroll.verticalScrollBar().valueChanged.connect(
            self._on_scrolled
        )

        return page

    def _build_preview_view(self) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(8, 8, 8, 8)
        col.setSpacing(8)

        back_btn = QPushButton("  Back")
        back_btn.setObjectName("btnGhost")
        back_btn.setIcon(icons.qicon("chevron_left", size=14, color="#62625F"))
        back_btn.setIconSize(icons.icon_size(14))
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        col.addWidget(back_btn, 0, Qt.AlignmentFlag.AlignLeft)

        meta_frame = QFrame()
        meta_frame.setObjectName("roundCard")
        apply_card_shadow(meta_frame)
        meta_col = QVBoxLayout(meta_frame)
        meta_col.setContentsMargins(14, 12, 14, 12)
        meta_col.setSpacing(4)
        self.meta_name = QLabel("")
        self.meta_name.setStyleSheet(
            "font-size: 14px; font-weight: 700; background: transparent;"
        )
        self.meta_name.setWordWrap(True)
        meta_col.addWidget(self.meta_name)
        self.meta_app = QLabel("")
        self.meta_app.setObjectName("mutedText")
        self.meta_app.setWordWrap(True)
        meta_col.addWidget(self.meta_app)
        self.meta_path = QLabel("")
        self.meta_path.setObjectName("monoSm")
        self.meta_path.setWordWrap(True)
        meta_col.addWidget(self.meta_path)
        self.meta_size = QLabel("")
        self.meta_size.setObjectName("subtle")
        meta_col.addWidget(self.meta_size)
        col.addWidget(meta_frame)

        self.preview_host = QFrame()
        self.preview_host.setObjectName("roundCard")
        self.preview_layout = QVBoxLayout(self.preview_host)
        self.preview_layout.setContentsMargins(8, 8, 8, 8)
        self.preview_layout.setSpacing(6)
        col.addWidget(self.preview_host, 1)

        return page

    def refresh(self) -> None:
        if not self.state.case_id:
            return
        self._all_files = []
        self._filtered_files = []
        self._shown_count = 0
        self._workers = []
        self._render_status("Loading files…")
        params: dict = {}
        if self._file_type:
            params["file_type"] = self._file_type
        api.run_async(
            api.get,
            on_result=self._on_files_loaded,
            on_error=lambda msg: self._render_status(f"Failed to load: {msg}"),
            path=f"/analysis/files/{self.state.case_id}",
            params=params or None,
        )

    def _set_file_type(self, value: Optional[str]) -> None:
        self._file_type = value
        self.refresh()

    def _on_search_changed(self, text: str) -> None:
        self._search = (text or "").strip().lower()
        self._reapply_filter(reset=True)

    def _on_files_loaded(self, data) -> None:
        self._all_files = api.coerce_list(data, "files", "items") or []
        self._reapply_filter(reset=True)
        if isinstance(data, dict) and not self._all_files and data.get("message"):
            self._render_status(data["message"])

    def _reapply_filter(self, *, reset: bool) -> None:
        if self._search:
            self._filtered_files = [
                f for f in self._all_files
                if self._search in (f.get("name") or "").lower()
            ]
        else:
            self._filtered_files = list(self._all_files)
        if reset:
            self._shown_count = min(self.PAGE_SIZE, len(self._filtered_files))
        else:
            self._shown_count = min(self._shown_count, len(self._filtered_files))
        self._render_list()

    def _reveal_more(self) -> None:
        prev_shown = self._shown_count
        new_shown = min(
            self._shown_count + self.PAGE_SIZE, len(self._filtered_files)
        )
        if new_shown == prev_shown:
            return
        for f in self._filtered_files[prev_shown:new_shown]:
            row = _FileRow(f)
            row.clicked.connect(self._open_preview)
            self.list_layout.insertWidget(self.list_layout.count() - 1, row)
        self._shown_count = new_shown
        self._update_count_label()

    def _render_list(self) -> None:
        self._clear_list()
        type_label = self._file_type or "files"

        if not self._filtered_files:
            self.count_label.setText(f"0 {type_label}")
            self._render_status(
                "No files match" if self._search or self._all_files else "No files"
            )
            return

        for f in self._filtered_files[: self._shown_count]:
            row = _FileRow(f)
            row.clicked.connect(self._open_preview)
            self.list_layout.insertWidget(self.list_layout.count() - 1, row)

        self._update_count_label()

    def _update_count_label(self) -> None:
        total = len(self._all_files)
        filt = len(self._filtered_files)
        type_label = self._file_type or "files"
        if self._shown_count < filt:
            self.count_label.setText(
                f"{fmt(self._shown_count)} of {fmt(filt)} {type_label}"
            )
        elif filt < total:
            self.count_label.setText(
                f"{fmt(filt)} of {fmt(total)} {type_label}"
            )
        else:
            self.count_label.setText(f"{fmt(total)} {type_label}")

    def _on_scrolled(self, value: int) -> None:
        sb = self.list_scroll.verticalScrollBar()
        max_val = sb.maximum()
        if max_val <= 0:
            return
        if value < max_val - 200:
            return
        if self._shown_count >= len(self._filtered_files):
            return
        self._reveal_more()

    def _render_status(self, message: str) -> None:
        self._clear_list()
        lbl = QLabel(message)
        lbl.setObjectName("mutedText")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("background: transparent; padding: 32px 0;")
        self.list_layout.insertWidget(self.list_layout.count() - 1, lbl)

    def _clear_list(self) -> None:
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _open_preview(self, file: dict) -> None:
        self.meta_name.setText(file.get("name") or "")
        self.meta_app.setText(_infer_source_app(file.get("path") or ""))
        self.meta_path.setText(file.get("path") or "")
        self.meta_size.setText(
            f"{fmt_bytes(file.get('size_bytes') or 0)} · "
            f"{(file.get('type') or 'other').title()}"
        )
        self._populate_preview_body(file)
        self.stack.setCurrentIndex(1)

    def _media_url(self, file: dict) -> Optional[str]:
        case_id = self.state.case_id
        acq_id = file.get("acquisition_id")
        path = file.get("path") or ""
        if not (case_id and acq_id and path):
            return None
        return f"/analysis/media/{case_id}/{acq_id}/{urlquote(path, safe='/')}"

    def _populate_preview_body(self, file: dict) -> None:
        while self.preview_layout.count():
            item = self.preview_layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        ftype = (file.get("type") or "other").lower()
        ext = os.path.splitext(file.get("name") or "")[1].lower()
        url = self._media_url(file)

        if ftype == "image" and url:
            self._render_image_preview(url)
            self._add_save_button(file, url)
            return

        if ftype == "document" and ext in _PREVIEWABLE_TEXT_EXT and url:
            self._render_text_preview(url)
            self._add_save_button(file, url)
            return

        msg = QLabel(self._fallback_message(ftype, ext, file))
        msg.setObjectName("mutedText")
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet("background: transparent; padding: 24px 12px;")
        self.preview_layout.addWidget(msg, 1)
        if url:
            self._add_save_button(file, url)
        else:
            warn = QLabel("Cannot resolve media URL for this file.")
            warn.setObjectName("subtle")
            warn.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.preview_layout.addWidget(warn)

    @staticmethod
    def _fallback_message(ftype: str, ext: str, file: dict) -> str:
        size = fmt_bytes(file.get("size_bytes") or 0)
        if ftype == "video":
            return f"Video file - {size}\nInline playback not supported. Save to disk to view."
        if ftype == "audio":
            return f"Audio file - {size}\nInline playback not supported. Save to disk to listen."
        if ftype == "document":
            label = (ext or "document").lstrip(".").upper() or "DOCUMENT"
            return f"{label} document - {size}\nInline preview not supported. Save to disk to open."
        return f"{(ftype or 'file').title()} - {size}\nNo inline preview. Save to disk to open."

    def _render_image_preview(self, url: str) -> None:
        label = QLabel("Loading…")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("background: #1C1C1A; color: #98988F; border-radius: 8px;")
        label.setMinimumSize(480, 360)
        self.preview_layout.addWidget(label, 1)

        def _on_data(data: bytes) -> None:
            pix = QPixmap()
            if not pix.loadFromData(data):
                label.setText("Decode failed")
                return
            label.setPixmap(
                pix.scaled(
                    label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        worker = api.run_async(
            api.get_bytes,
            on_result=_on_data,
            on_error=lambda _msg: label.setText("Failed to load"),
            path=url,
        )
        self._workers.append(worker)

    def _render_text_preview(self, url: str) -> None:
        editor = QTextEdit()
        editor.setReadOnly(True)
        editor.setPlaceholderText("Loading…")
        editor.setStyleSheet(
            "background: #FFFFFF; border: 1px solid #E8E8E2; "
            "font-family: 'JetBrains Mono','Consolas',monospace; font-size: 12px;"
        )
        self.preview_layout.addWidget(editor, 1)

        def _on_data(data: bytes) -> None:
            try:
                text = data.decode("utf-8", errors="replace")
            except Exception as exc:
                editor.setPlainText(f"(Could not decode: {exc})")
                return
            lines = text.splitlines()
            if len(lines) > _TXT_PREVIEW_MAX_LINES:
                trimmed = "\n".join(lines[:_TXT_PREVIEW_MAX_LINES])
                trimmed += (
                    f"\n\n… (truncated, showing first {_TXT_PREVIEW_MAX_LINES} "
                    f"of {len(lines)} lines)"
                )
                editor.setPlainText(trimmed)
            else:
                editor.setPlainText(text)

        worker = api.run_async(
            api.get_bytes,
            on_result=_on_data,
            on_error=lambda msg: editor.setPlainText(f"(Failed to load: {msg})"),
            path=url,
        )
        self._workers.append(worker)

    def _add_save_button(self, file: dict, url: str) -> None:
        btn = QPushButton("Save to disk")
        btn.setObjectName("pillSecondary")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self._save_to_disk(file, url, btn))
        self.preview_layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)

    def _save_to_disk(self, file: dict, url: str, btn: QPushButton) -> None:
        suggested = file.get("name") or "file"
        target_path, _filter = QFileDialog.getSaveFileName(
            self, "Save file", suggested
        )
        if not target_path:
            return
        btn.setEnabled(False)
        btn.setText("Saving…")

        def _write(data: bytes) -> None:
            btn.setEnabled(True)
            btn.setText("Save to disk")
            try:
                with open(target_path, "wb") as fh:
                    fh.write(data)
            except OSError as exc:
                self.toast.emit(f"Save failed: {exc}")
                return
            self.toast.emit(f"Saved {os.path.basename(target_path)}")

        def _err(msg: str) -> None:
            btn.setEnabled(True)
            btn.setText("Save to disk")
            self.toast.emit(f"Save failed: {msg}")

        worker = api.run_async(
            api.get_bytes,
            on_result=_write,
            on_error=_err,
            path=url,
        )
        self._workers.append(worker)

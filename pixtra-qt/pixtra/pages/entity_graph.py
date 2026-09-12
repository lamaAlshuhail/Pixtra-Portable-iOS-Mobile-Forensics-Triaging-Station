import json
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import api, icons
from ..state import AppState

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    WEBENGINE_AVAILABLE = True
except ImportError:
    QWebEngineView = None
    QWebEngineSettings = None
    WEBENGINE_AVAILABLE = False


ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
GRAPH_HTML = ASSETS_DIR / "graph.html"


class EntityGraphPage(QWidget):
    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._pending_payload: Optional[dict] = None
        self._page_loaded = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.empty_card = QFrame()
        self.empty_card.setObjectName("card")
        ec = QVBoxLayout(self.empty_card)
        ec.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ec.setContentsMargins(20, 40, 20, 40)
        ec.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("share2", size=40, color="#98988F", stroke=1.5))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ec.addWidget(ic)
        self.empty_text = QLabel("No entities yet - run extraction to build the graph")
        self.empty_text.setObjectName("mutedText")
        self.empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_text.setWordWrap(True)
        ec.addWidget(self.empty_text)
        self.run_btn = QPushButton("Run Entity Extraction")
        self.run_btn.setObjectName("btnPrimary")
        self.run_btn.clicked.connect(self._run_extraction)
        ec.addWidget(self.run_btn, 0, Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty_card)

        if WEBENGINE_AVAILABLE:
            self.web_view = QWebEngineView()
            settings = self.web_view.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
            settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
            self.web_view.loadFinished.connect(self._on_page_loaded)
            self.web_view.setVisible(False)
            root.addWidget(self.web_view, 1)
        else:
            self.web_view = None
            fallback = QLabel(
                "QtWebEngine not installed. Run:\n"
                "    pip3 install --break-system-packages PyQt6-WebEngine"
            )
            fallback.setObjectName("mutedText")
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback.setWordWrap(True)
            fallback.setVisible(False)
            self._fallback_label = fallback
            root.addWidget(fallback, 1)

        state.case_changed.connect(lambda _: self._load())

    def on_show(self) -> None:
        self._load()

    def _load(self) -> None:
        if not self.state.case_id:
            return
        api.run_async(
            api.get,
            on_result=self._on_loaded,
            on_error=lambda msg: self._show_empty(f"Could not load graph: {msg}"),
            path=f"/analysis/graph/{self.state.case_id}",
        )

    def _run_extraction(self) -> None:
        if not self.state.case_id:
            return
        self.run_btn.setEnabled(False)
        self.empty_text.setText("Running entity extraction (this can take a moment)...")
        api.run_async(
            api.post,
            on_result=self._on_loaded,
            on_error=lambda msg: self._show_empty(f"Extraction failed: {msg}"),
            path=f"/analysis/entities/{self.state.case_id}",
        )

    def _show_empty(self, message: str) -> None:
        self.empty_card.setVisible(True)
        self.empty_text.setText(message)
        self.run_btn.setEnabled(True)
        if self.web_view is not None:
            self.web_view.setVisible(False)

    def _on_loaded(self, data) -> None:
        data = data or {}
        if isinstance(data, dict) and isinstance(data.get("graph"), dict):
            graph = data["graph"]
        elif isinstance(data, dict):
            graph = data
        else:
            graph = {}
        nodes = graph.get("nodes") if isinstance(graph, dict) else []
        edges = graph.get("edges") if isinstance(graph, dict) else []
        if edges is None:
            edges = graph.get("links") if isinstance(graph, dict) else []
        nodes = nodes or []
        edges = edges or []

        if len(nodes) < 2:
            self._show_empty(
                "Sparse evidence - entity graph needs more data."
                if len(nodes) == 1
                else "No entities yet - run extraction to build the graph"
            )
            return

        links = [
            {
                "source": e.get("source_entity_id") or e.get("source"),
                "target": e.get("target_entity_id") or e.get("target"),
                "weight": e.get("weight") or 1,
            }
            for e in edges
            if (e.get("source_entity_id") or e.get("source"))
            and (e.get("target_entity_id") or e.get("target"))
        ]
        payload = {"nodes": nodes, "links": links}

        if self.web_view is None:
            self.empty_card.setVisible(False)
            self._fallback_label.setVisible(True)
            return

        self.empty_card.setVisible(False)
        self.web_view.setVisible(True)
        self._pending_payload = payload

        if self._page_loaded:
            self._inject_payload()
        else:
            if not GRAPH_HTML.exists():
                self._show_empty(f"graph.html missing at {GRAPH_HTML}")
                return
            self.web_view.load(QUrl.fromLocalFile(str(GRAPH_HTML)))

    def _on_page_loaded(self, ok: bool) -> None:
        self._page_loaded = ok
        if ok and self._pending_payload is not None:
            self._inject_payload()

    def _inject_payload(self) -> None:
        if self.web_view is None or self._pending_payload is None:
            return
        js = f"window.loadGraph({json.dumps(self._pending_payload)});"
        self.web_view.page().runJavaScript(js)

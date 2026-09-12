import json
import os
from html import escape
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtWebEngineWidgets import QWebEngineView

try:
    from PyQt6.QtWebEngineCore import QWebEngineSettings
except ImportError:
    QWebEngineSettings = None
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import api
from ..api import API_BASE
from ..format import fmt
from ..state import AppState


_FILTER_CHIPS: list[tuple[str, Optional[str]]] = [
    ("All", None),
    ("Photos", "exif"),
    ("Network", "wifi"),
    ("Other", "_other"),
    ("Stay Points", "_dwell"),
]

_DWELL_FILTER = "_dwell"

_MAX_MARKERS = 500

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
_ASSETS_BASE_URL = QUrl.fromLocalFile(str(_ASSETS_DIR) + "/")

_TILE_URL = os.environ.get("PIXTRA_MAP_TILE_URL", "").strip()
_TILE_ATTRIBUTION = os.environ.get("PIXTRA_MAP_TILE_ATTRIBUTION", "").strip()

_TILE_LAYER_JS = """
  const TILE_URL = __TILE_URL__;
  if (TILE_URL) {
    L.tileLayer(TILE_URL, { maxZoom: 19, attribution: __TILE_ATTR__ }).addTo(map);
  } else {
    const note = L.control({ position: 'bottomleft' });
    note.onAdd = () => {
      const d = L.DomUtil.create('div');
      d.style.cssText = 'background:rgba(0,0,0,.6);color:#98988F;font:11px sans-serif;padding:4px 8px;border-radius:4px;';
      d.textContent = 'Offline map - no basemap tiles (set PIXTRA_MAP_TILE_URL to enable)';
      return d;
    };
    note.addTo(map);
  }
"""


def _fill_template(template: str) -> str:
    return (
        template
        .replace("__TILE_LAYER__", _TILE_LAYER_JS)
        .replace("__TILE_URL__", json.dumps(_TILE_URL))
        .replace("__TILE_ATTR__", json.dumps(_TILE_ATTRIBUTION))
    )

_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="leaflet.css" />
<script src="leaflet.js"></script>
<style>
  body, html, #map { margin: 0; padding: 0; height: 100%; width: 100%; }
  body { background: #1C1C1A; }
  #map { background: #23262B; }
  .leaflet-popup-content {
    font: 12px/1.4 -apple-system, sans-serif;
    min-width: 180px;
    text-align: center;
  }
</style>
</head>
<body>
<div id="map"></div>
<script>
  const points = __POINTS_JSON__;
  const map = L.map('map');
__TILE_LAYER__
  if (points.length === 0) {
    map.setView([0, 0], 2);
  } else {
    const markers = points.map(p => L.marker([p.lat, p.lon]).bindPopup(p.popup));
    const grp = L.featureGroup(markers).addTo(map);
    map.fitBounds(grp.getBounds(), { padding: [20, 20] });
  }
</script>
</body>
</html>
"""


_DWELL_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="leaflet.css" />
<script src="leaflet.js"></script>
<style>
  body, html, #map { margin: 0; padding: 0; height: 100%; width: 100%; }
  body { background: #1C1C1A; }
  #map { background: #23262B; }
  .leaflet-popup-content { font: 12px/1.4 -apple-system, sans-serif; }
</style>
</head>
<body>
<div id="map" tabindex="-1"></div>
<script>
  const stays = __STAYS_JSON__;
  const trips = __TRIPS_JSON__;
  const showTrips = __SHOW_TRIPS__;
  const map = L.map('map');
__TILE_LAYER__

  const colorFor = (sec) => sec < 7200 ? '#FFC107' : (sec < 28800 ? '#FF9800' : '#E53935');
  const radiusFor = (sec) => sec < 7200 ? 8 : (sec < 28800 ? 12 : 16);

  const markers = stays.map(s => L.circleMarker([s.centroid_lat, s.centroid_lon], {
    radius: radiusFor(s.duration_seconds),
    fillColor: colorFor(s.duration_seconds),
    fillOpacity: 0.85,
    color: s.is_frequent ? '#000' : '#fff',
    weight: s.is_frequent ? 3 : 1,
  }).bindPopup(s.popup));

  if (showTrips && trips.length > 0) {
    const stayById = {};
    stays.forEach(s => { stayById[s.id] = s; });
    trips.forEach(t => {
      const a = stayById[t.from_stay_id];
      const b = stayById[t.to_stay_id];
      if (!a || !b) return;
      L.polyline([[a.centroid_lat, a.centroid_lon], [b.centroid_lat, b.centroid_lon]], {
        color: '#1B5E3B', weight: 2, opacity: 0.6
      }).bindPopup(t.popup).addTo(map);
    });
  }

  if (markers.length === 0) {
    map.setView([0, 0], 2);
  } else {
    const grp = L.featureGroup(markers).addTo(map);
    map.fitBounds(grp.getBounds(), { padding: [20, 20], maxZoom: 14 });
  }
</script>
</body>
</html>
"""


class LocationsPage(QWidget):
    navigate_requested = pyqtSignal(str)

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._all: list[dict] = []
        self._source_filter: Optional[str] = None
        self._dwell_data: Optional[dict] = None
        self._show_trips: bool = False
        self._data_rendered = False
        self.web = QWebEngineView(self)
        self.web.setParent(self)
        if QWebEngineSettings is not None:
            st = self.web.settings()
            st.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            st.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        title_row = QHBoxLayout()
        title = QLabel("Locations")
        title.setStyleSheet(
            "font-size: 22px; font-weight: 800; background: transparent;"
        )
        title_row.addWidget(title)
        self.count_label = QLabel("0 GPS points")
        self.count_label.setObjectName("mutedText")
        self.count_label.setStyleSheet(
            "background: transparent; padding-left: 8px;"
        )
        title_row.addWidget(self.count_label)
        title_row.addStretch(1)
        root.addLayout(title_row)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)
        for label, value in _FILTER_CHIPS:
            btn = QPushButton(label)
            btn.setObjectName("chipFilter")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if value is None:
                btn.setChecked(True)
            btn.clicked.connect(lambda _checked, v=value: self._set_filter(v))
            self._chip_group.addButton(btn)
            chips.addWidget(btn)
        chips.addStretch(1)
        self.trips_btn = QPushButton("Show trips")
        self.trips_btn.setObjectName("chipFilter")
        self.trips_btn.setCheckable(True)
        self.trips_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.trips_btn.setVisible(False)
        self.trips_btn.toggled.connect(self._on_trips_toggled)
        chips.addWidget(self.trips_btn)
        root.addLayout(chips)

        root.addWidget(self.web, 1)

        state.case_changed.connect(lambda _: self.refresh())

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        if not self.state.case_id:
            return
        self._dwell_data = None
        self._data_rendered = False
        self.count_label.setText("Loading…")
        QTimer.singleShot(0, self._show_loading_html)
        api.run_async(
            api.get,
            on_result=self._on_loaded,
            on_error=lambda _msg: self._set_error("Failed to load locations"),
            path=f"/analysis/evidence/{self.state.case_id}/locations",
        )

    def _show_loading_html(self) -> None:
        if self._data_rendered:
            return
        self.web.setHtml(
            "<html><body style='background:#1C1C1A;color:#98988F;"
            "font-family:sans-serif;padding:40px;text-align:center;'>"
            "Loading map…</body></html>"
        )

    def _on_loaded(self, data) -> None:
        rows = api.coerce_list(data, "locations", "items")
        self._all = [
            r for r in rows
            if r.get("latitude") is not None and r.get("longitude") is not None
        ]
        if self._source_filter == _DWELL_FILTER:
            return
        self._render()

    def _set_filter(self, value: Optional[str]) -> None:
        self._source_filter = value
        if value == _DWELL_FILTER:
            self.trips_btn.setVisible(True)
            self._render_dwell_or_load()
        else:
            self.trips_btn.setVisible(False)
            self._render()

    def _on_trips_toggled(self, checked: bool) -> None:
        self._show_trips = checked
        if self._source_filter == _DWELL_FILTER and self._dwell_data is not None:
            self._render_dwell()

    def _render_dwell_or_load(self) -> None:
        if self._dwell_data is not None:
            self._render_dwell()
            return
        if not self.state.case_id:
            return
        self._data_rendered = False
        self.count_label.setText("Analyzing dwell time…")
        QTimer.singleShot(0, self._show_loading_html)
        api.run_async(
            api.get,
            on_result=self._on_dwell_loaded,
            on_error=lambda _msg: self._set_error("Failed to load stay points"),
            path=f"/analysis/evidence/{self.state.case_id}/dwell-points",
        )

    def _on_dwell_loaded(self, data) -> None:
        self._dwell_data = data if isinstance(data, dict) else {}
        if self._source_filter != _DWELL_FILTER:
            return
        self._render_dwell()

    def _render_dwell(self) -> None:
        data = self._dwell_data or {}
        stays = list(data.get("stay_points") or [])
        trips = list(data.get("trips") or [])
        stats = data.get("stats") or {}

        for s in stays:
            s["popup"] = self._stay_popup_html(s)
        for t in trips:
            t["popup"] = self._trip_popup_html(t)

        self.count_label.setText(
            f"{fmt(int(stats.get('total_stay_points') or 0))} stay points, "
            f"{fmt(int(stats.get('total_trips') or 0))} trips · "
            f"{float(stats.get('total_dwell_hours') or 0):.0f}h tracked"
        )

        html = (
            _DWELL_HTML_TEMPLATE
            .replace("__STAYS_JSON__", json.dumps(stays))
            .replace("__TRIPS_JSON__", json.dumps(trips))
            .replace("__SHOW_TRIPS__", "true" if self._show_trips else "false")
        )
        self._data_rendered = True
        self.web.setHtml(_fill_template(html), _ASSETS_BASE_URL)

    @staticmethod
    def _stay_popup_html(s: dict) -> str:
        lines: list[str] = [
            f"<b>{escape(str(s.get('duration_human') or ''))}</b>",
        ]
        if s.get("arrived"):
            lines.append(f"Arrived: {escape(str(s['arrived']))}")
        if s.get("departed"):
            lines.append(f"Departed: {escape(str(s['departed']))}")
        photos = int(s.get("photo_count") or 0)
        if photos:
            lines.append(f"{fmt(photos)} photos")
        if s.get("is_frequent"):
            lines.append("&#11088; Frequent location")
        return "<br>".join(lines)

    @staticmethod
    def _trip_popup_html(t: dict) -> str:
        dist = t.get("distance_km")
        dur = t.get("duration_human") or ""
        speed = t.get("avg_speed_kmh")
        head = (
            f"<b>{float(dist):.1f} km in {escape(str(dur))}</b>"
            if dist is not None else f"<b>{escape(str(dur))}</b>"
        )
        if speed is not None:
            return f"{head}<br>Avg {float(speed):.0f} km/h"
        return head

    def _filtered(self) -> list[dict]:
        flt = self._source_filter
        if flt is None:
            return self._all
        if flt == "_other":
            return [
                r for r in self._all
                if (r.get("source") or "") not in ("exif", "wifi")
            ]
        return [r for r in self._all if (r.get("source") or "") == flt]

    def _render(self) -> None:
        rows = self._filtered()
        if len(rows) > _MAX_MARKERS:
            step = len(rows) / _MAX_MARKERS
            sampled = [rows[int(i * step)] for i in range(_MAX_MARKERS)]
        else:
            sampled = rows

        points: list[dict] = []
        for r in sampled:
            try:
                lat = float(r.get("latitude"))
                lon = float(r.get("longitude"))
            except (TypeError, ValueError):
                continue
            points.append({
                "lat": lat,
                "lon": lon,
                "popup": self._popup_html(r),
            })

        total = len(self._all)
        shown = len(self._filtered())
        if shown == total:
            self.count_label.setText(f"{fmt(total)} GPS points")
        else:
            self.count_label.setText(f"{fmt(shown)} of {fmt(total)} GPS points")

        html = _HTML_TEMPLATE.replace("__POINTS_JSON__", json.dumps(points))
        self._data_rendered = True
        self.web.setHtml(_fill_template(html), _ASSETS_BASE_URL)

    def _set_error(self, message: str) -> None:
        self._data_rendered = True
        self.count_label.setText(message)
        self.web.setHtml(
            f"<html><body style='background:#1C1C1A;color:#C62828;"
            f"font-family:sans-serif;padding:40px;text-align:center;'>"
            f"{escape(message)}</body></html>"
        )

    def _popup_html(self, r: dict) -> str:
        lines: list[str] = []
        photo_id = r.get("photo_id")
        case_id = self.state.case_id
        if photo_id and r.get("source") == "exif" and case_id:
            thumb_url = (
                f"{API_BASE}/analysis/evidence/"
                f"{case_id}/photos/{photo_id}/thumb"
            )
            lines.append(
                f'<img src="{thumb_url}" '
                f'style="width:160px;height:160px;object-fit:cover;'
                f'border-radius:6px;display:block;margin:0 auto 6px;" />'
            )
        if r.get("timestamp"):
            lines.append(f"<b>{escape(str(r['timestamp']))}</b>")
        if r.get("label"):
            lines.append(f"&#128247; {escape(str(r['label']))}")
        if r.get("source"):
            lines.append(f"Source: {escape(str(r['source']))}")
        try:
            lines.append(
                f"GPS: {float(r.get('latitude')):.5f}, "
                f"{float(r.get('longitude')):.5f}"
            )
        except (TypeError, ValueError):
            pass
        return "<br>".join(lines)

from typing import Optional

from PyQt6.QtCore import QByteArray, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

_INNER = {
    "layout_dashboard": (
        '<rect x="3" y="3" width="7" height="9" rx="1"/>'
        '<rect x="14" y="3" width="7" height="5" rx="1"/>'
        '<rect x="14" y="12" width="7" height="9" rx="1"/>'
        '<rect x="3" y="16" width="7" height="5" rx="1"/>'
    ),
    "folder_open": (
        '<path d="M6 14l-2 6h14l2-6"/>'
        '<path d="M2 11V5a2 2 0 0 1 2-2h3.93a2 2 0 0 1 1.66.9l.82 1.2a2 2 0 0 0 1.66.9H20a2 2 0 0 1 2 2v3"/>'
    ),
    "folder_plus": (
        '<path d="M12 10v6M9 13h6"/>'
        '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z"/>'
    ),
    "smartphone": (
        '<rect x="5" y="2" width="14" height="20" rx="2" ry="2"/>'
        '<line x1="12" y1="18" x2="12.01" y2="18"/>'
    ),
    "download": (
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
        '<polyline points="7 10 12 15 17 10"/>'
        '<line x1="12" y1="15" x2="12" y2="3"/>'
    ),
    "message_square": (
        '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>'
    ),
    "message_circle": (
        '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>'
    ),
    "users": (
        '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
        '<circle cx="9" cy="7" r="4"/>'
        '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/>'
        '<path d="M16 3.13a4 4 0 0 1 0 7.75"/>'
    ),
    "phone": (
        '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>'
    ),
    "phone_missed": (
        '<line x1="22" y1="2" x2="16" y2="8"/>'
        '<line x1="16" y1="2" x2="22" y2="8"/>'
        '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>'
    ),
    "arrow_down_left": (
        '<line x1="17" y1="7" x2="7" y2="17"/>'
        '<polyline points="17 17 7 17 7 7"/>'
    ),
    "arrow_up_right": (
        '<line x1="7" y1="17" x2="17" y2="7"/>'
        '<polyline points="7 7 17 7 17 17"/>'
    ),
    "globe": (
        '<circle cx="12" cy="12" r="10"/>'
        '<line x1="2" y1="12" x2="22" y2="12"/>'
        '<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>'
    ),
    "clock": (
        '<circle cx="12" cy="12" r="10"/>'
        '<polyline points="12 6 12 12 16 14"/>'
    ),
    "share2": (
        '<circle cx="18" cy="5" r="3"/>'
        '<circle cx="6" cy="12" r="3"/>'
        '<circle cx="18" cy="19" r="3"/>'
        '<line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>'
        '<line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>'
    ),
    "shield_check": (
        '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>'
        '<polyline points="9 12 11 14 15 10"/>'
    ),
    "file_text": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<polyline points="14 2 14 8 20 8"/>'
        '<line x1="16" y1="13" x2="8" y2="13"/>'
        '<line x1="16" y1="17" x2="8" y2="17"/>'
        '<polyline points="10 9 9 9 8 9"/>'
    ),
    "zap": (
        '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>'
    ),
    "search": (
        '<circle cx="11" cy="11" r="8"/>'
        '<line x1="21" y1="21" x2="16.65" y2="16.65"/>'
    ),
    "plus": (
        '<line x1="12" y1="5" x2="12" y2="19"/>'
        '<line x1="5" y1="12" x2="19" y2="12"/>'
    ),
    "lock": (
        '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>'
        '<path d="M7 11V7a5 5 0 0 1 10 0v4"/>'
    ),
    "user_circle": (
        '<circle cx="12" cy="12" r="10"/>'
        '<circle cx="12" cy="10" r="3"/>'
        '<path d="M6.168 18.849A4 4 0 0 1 10 16h4a4 4 0 0 1 3.834 2.855"/>'
    ),
    "x": (
        '<line x1="18" y1="6" x2="6" y2="18"/>'
        '<line x1="6" y1="6" x2="18" y2="18"/>'
    ),
    "chevron_left": (
        '<polyline points="15 18 9 12 15 6"/>'
    ),
    "chevron_right": (
        '<polyline points="9 18 15 12 9 6"/>'
    ),
    "chevron_up": (
        '<polyline points="18 15 12 9 6 15"/>'
    ),
    "chevron_down": (
        '<polyline points="6 9 12 15 18 9"/>'
    ),
    "chevrons_up_down": (
        '<polyline points="7 15 12 20 17 15"/>'
        '<polyline points="7 9 12 4 17 9"/>'
    ),
    "check": (
        '<polyline points="20 6 9 17 4 12"/>'
    ),
    "check_circle": (
        '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>'
        '<polyline points="22 4 12 14.01 9 11.01"/>'
    ),
    "alert_triangle": (
        '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>'
        '<line x1="12" y1="9" x2="12" y2="13"/>'
        '<line x1="12" y1="17" x2="12.01" y2="17"/>'
    ),
    "clipboard": (
        '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>'
        '<rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>'
    ),
    "refresh": (
        '<polyline points="23 4 23 10 17 10"/>'
        '<polyline points="1 20 1 14 7 14"/>'
        '<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>'
    ),
    "arrow_left": (
        '<line x1="19" y1="12" x2="5" y2="12"/>'
        '<polyline points="12 19 5 12 12 5"/>'
    ),
    "home": (
        '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
        '<polyline points="9 22 9 12 15 12 15 22"/>'
    ),
    "mail": (
        '<rect x="2" y="4" width="20" height="16" rx="2"/>'
        '<polyline points="22 6 12 13 2 6"/>'
    ),
    "image": (
        '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>'
        '<circle cx="9" cy="9" r="2"/>'
        '<polyline points="21 15 16 10 5 21"/>'
    ),
    "calendar": (
        '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>'
        '<line x1="16" y1="2" x2="16" y2="6"/>'
        '<line x1="8" y1="2" x2="8" y2="6"/>'
        '<line x1="3" y1="10" x2="21" y2="10"/>'
    ),
    "map_pin": (
        '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>'
        '<circle cx="12" cy="10" r="3"/>'
    ),
    "grid_3x3": (
        '<rect x="3" y="3" width="18" height="18" rx="2"/>'
        '<line x1="3" y1="9" x2="21" y2="9"/>'
        '<line x1="3" y1="15" x2="21" y2="15"/>'
        '<line x1="9" y1="3" x2="9" y2="21"/>'
        '<line x1="15" y1="3" x2="15" y2="21"/>'
    ),
    "key": (
        '<circle cx="7.5" cy="15.5" r="5.5"/>'
        '<path d="M21 2l-9.6 9.6"/>'
        '<path d="M15.5 7.5l3 3L22 7l-3-3"/>'
    ),
    "wifi": (
        '<path d="M5 12.55a11 11 0 0 1 14.08 0"/>'
        '<path d="M1.42 9a16 16 0 0 1 21.16 0"/>'
        '<path d="M8.53 16.11a6 6 0 0 1 6.95 0"/>'
        '<line x1="12" y1="20" x2="12.01" y2="20"/>'
    ),
    "git_fork": (
        '<circle cx="12" cy="18" r="3"/>'
        '<circle cx="6" cy="6" r="3"/>'
        '<circle cx="18" cy="6" r="3"/>'
        '<path d="M18 9v2c0 .6-.4 1-1 1H7c-.6 0-1-.4-1-1V9"/>'
        '<path d="M12 12v3"/>'
    ),
    "file_output": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<polyline points="14 2 14 8 20 8"/>'
        '<polyline points="9 18 12 21 15 18"/>'
        '<line x1="12" y1="13" x2="12" y2="21"/>'
    ),
    "camera": (
        '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>'
        '<circle cx="12" cy="13" r="4"/>'
    ),
    "book_user": (
        '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>'
        '<path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>'
        '<circle cx="12" cy="9" r="2.5"/>'
        '<path d="M8.5 14.5a3.5 3.5 0 0 1 7 0"/>'
    ),
    "network": (
        '<rect x="9" y="2" width="6" height="6" rx="1"/>'
        '<rect x="3" y="16" width="6" height="6" rx="1"/>'
        '<rect x="15" y="16" width="6" height="6" rx="1"/>'
        '<path d="M12 8v4M6 16v-2h12v2"/>'
    ),
    "eye": (
        '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>'
        '<circle cx="12" cy="12" r="3"/>'
    ),
    "eye_off": (
        '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>'
        '<path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>'
        '<path d="M14.12 14.12a3 3 0 1 1-4.24-4.24"/>'
        '<line x1="1" y1="1" x2="23" y2="23"/>'
    ),
    "hard_drive": (
        '<line x1="22" y1="12" x2="2" y2="12"/>'
        '<path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>'
        '<line x1="6" y1="16" x2="6.01" y2="16"/>'
        '<line x1="10" y1="16" x2="10.01" y2="16"/>'
    ),
    "video": (
        '<path d="m22 8-6 4 6 4V8Z"/>'
        '<rect x="2" y="6" width="14" height="12" rx="2" ry="2"/>'
    ),
    "music": (
        '<path d="M9 18V5l12-2v13"/>'
        '<circle cx="6" cy="18" r="3"/>'
        '<circle cx="18" cy="16" r="3"/>'
    ),
    "credit_card": (
        '<rect x="2" y="5" width="20" height="14" rx="2"/>'
        '<line x1="2" y1="10" x2="22" y2="10"/>'
    ),
    "plane": (
        '<path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"/>'
    ),
    "ticket": (
        '<path d="M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2z"/>'
        '<path d="M13 5v2"/>'
        '<path d="M13 17v2"/>'
        '<path d="M13 11v2"/>'
    ),
    "gift": (
        '<rect x="3" y="8" width="18" height="4" rx="1"/>'
        '<path d="M12 8v13"/>'
        '<path d="M19 12v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7"/>'
        '<path d="M7.5 8a2.5 2.5 0 1 1 0-5C11 3 12 8 12 8"/>'
        '<path d="M16.5 8a2.5 2.5 0 1 0 0-5C13 3 12 8 12 8"/>'
    ),
    "inbox": (
        '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/>'
        '<path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>'
    ),
    "help_circle": (
        '<circle cx="12" cy="12" r="10"/>'
        '<path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>'
        '<line x1="12" y1="17" x2="12.01" y2="17"/>'
    ),
}


def _svg(name: str, color: str, stroke: float = 1.75) -> bytes:
    inner = _INNER.get(name, "")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
        f"{inner}</svg>"
    ).encode("utf-8")


def pixmap(name: str, size: int = 18, color: str = "#1C1C1A", stroke: float = 1.75) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(_svg(name, color, stroke)))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    return pm


def qicon(name: str, size: int = 18, color: str = "#1C1C1A", stroke: float = 1.75) -> QIcon:
    return QIcon(pixmap(name, size=size, color=color, stroke=stroke))


def icon_size(size: int) -> QSize:
    return QSize(size, size)

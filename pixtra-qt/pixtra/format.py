from datetime import datetime
from typing import Any, Optional


def fmt(n: Any) -> str:
    if not n:
        return "0"
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def initials(name: Optional[str]) -> str:
    if not name:
        return "?"
    parts = [p for p in str(name).split() if p]
    if not parts:
        return "?"
    letters = "".join(p[0] for p in parts[:2])
    return letters.upper()


def fmt_time(ts: Any) -> str:
    if not ts:
        return ""
    try:
        if isinstance(ts, (int, float)):
            d = datetime.fromtimestamp(ts)
        else:
            text = str(ts).replace("Z", "+00:00")
            try:
                d = datetime.fromisoformat(text)
            except ValueError:
                return str(ts)
        return d.strftime("%b %d %H:%M")
    except Exception:
        return str(ts)


def fmt_iso8601(ts: Any) -> str:
    if not ts:
        return " - "
    try:
        if isinstance(ts, (int, float)):
            d = datetime.fromtimestamp(ts)
        else:
            text = str(ts).replace("Z", "+00:00")
            try:
                d = datetime.fromisoformat(text)
            except ValueError:
                return " - "
        return d.strftime("%Y-%m-%dT%H:%MZ")
    except Exception:
        return " - "


def fmt_duration(s: Any) -> str:
    try:
        s = int(s or 0)
    except (TypeError, ValueError):
        return "0s"
    if s < 60:
        return f"{s}s"
    m, sec = divmod(s, 60)
    if m < 60:
        return f"{m}m {sec}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


def fmt_bytes(b: Any) -> str:
    try:
        b = int(b or 0)
    except (TypeError, ValueError):
        return "0 B"
    if b < 1024:
        return f"{b} B"
    if b < 1024 ** 2:
        return f"{b / 1024:.1f} KB"
    if b < 1024 ** 3:
        return f"{b / 1024 ** 2:.1f} MB"
    return f"{b / 1024 ** 3:.1f} GB"

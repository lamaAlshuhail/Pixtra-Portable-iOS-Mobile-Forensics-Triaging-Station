from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal


class _SessionSignals(QObject):
    session_expired = pyqtSignal()
    must_change_password = pyqtSignal()
    authenticated = pyqtSignal()


_signals = _SessionSignals()
_token: Optional[str] = None
_examiner: Optional[dict] = None


def signals() -> _SessionSignals:
    return _signals


def get_token() -> Optional[str]:
    return _token


def set_token(token: Optional[str]) -> None:
    global _token
    _token = token


def clear_token() -> None:
    global _token, _examiner
    _token = None
    _examiner = None


def get_current_examiner() -> Optional[dict]:
    return _examiner


def set_current_examiner(examiner: Optional[dict]) -> None:
    global _examiner
    _examiner = examiner
    _signals.authenticated.emit()


def get_role() -> Optional[str]:
    if _examiner is None:
        return None
    return _examiner.get("role")


def is_supervisor() -> bool:
    return get_role() == "supervisor"


def is_viewer() -> bool:
    return get_role() == "viewer"


def can_mutate() -> bool:
    return get_role() in ("examiner", "supervisor")


def emit_session_expired() -> None:
    clear_token()
    _signals.session_expired.emit()


def emit_must_change_password() -> None:
    _signals.must_change_password.emit()

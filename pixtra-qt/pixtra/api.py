import json
import os
from typing import Any, Callable, Optional

import requests
from PyQt6.QtCore import (
    QObject,
    QRunnable,
    QThreadPool,
    pyqtSignal,
    pyqtSlot,
)

from .services import session as session_svc

API_BASE = os.environ.get("PIXTRA_API_BASE", "http://127.0.0.1:8080").rstrip("/") + "/api"
TIMEOUT = 10


def _url(path: str) -> str:
    if path.startswith("http"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    return API_BASE + path


def _auth_headers() -> dict:
    token = session_svc.get_token()
    return {"X-Pixtra-Token": token} if token else {}


def _check_response(r: requests.Response) -> None:
    if r.status_code in (401, 403):
        try:
            detail = (r.json() or {}).get("detail", "")
        except (ValueError, json.JSONDecodeError):
            detail = ""
        if r.status_code == 401 and session_svc.get_token():
            session_svc.emit_session_expired()
        if r.status_code == 403 and str(detail) == "must_change_password":
            session_svc.emit_must_change_password()
    r.raise_for_status()


def get(path: str, params: Optional[dict] = None) -> Any:
    r = requests.get(
        _url(path), params=params, timeout=TIMEOUT, headers=_auth_headers(),
    )
    _check_response(r)
    if not r.content:
        return None
    try:
        return r.json()
    except json.JSONDecodeError:
        return r.text


def post(path: str, body: Optional[dict] = None, params: Optional[dict] = None) -> Any:
    r = requests.post(
        _url(path), json=body, params=params, timeout=TIMEOUT,
        headers=_auth_headers(),
    )
    _check_response(r)
    if not r.content:
        return None
    try:
        return r.json()
    except json.JSONDecodeError:
        return r.text


def put(path: str, body: Optional[dict] = None, params: Optional[dict] = None) -> Any:
    r = requests.put(
        _url(path), json=body, params=params, timeout=TIMEOUT,
        headers=_auth_headers(),
    )
    _check_response(r)
    if not r.content:
        return None
    try:
        return r.json()
    except json.JSONDecodeError:
        return r.text


def delete(path: str, params: Optional[dict] = None) -> Any:
    r = requests.delete(
        _url(path), params=params, timeout=TIMEOUT, headers=_auth_headers(),
    )
    _check_response(r)
    if not r.content:
        return None
    try:
        return r.json()
    except json.JSONDecodeError:
        return r.text


def get_bytes(path: str, params: Optional[dict] = None, timeout: int = 30) -> bytes:
    r = requests.get(
        _url(path), params=params, timeout=timeout, headers=_auth_headers(),
    )
    _check_response(r)
    return r.content


def coerce_list(data: Any, *keys: str) -> list:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for k in keys:
        v = data.get(k)
        if isinstance(v, list):
            return v
    for v in data.values():
        if isinstance(v, list):
            return v
    return []


class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)


class _Worker(QRunnable):
    def __init__(self, fn: Callable, *args, **kwargs) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except requests.RequestException as exc:
            self.signals.error.emit(str(exc))
        except Exception as exc:
            self.signals.error.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.signals.finished.emit(result)


def run_async(
    fn: Callable,
    on_result: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
    *args,
    **kwargs,
) -> _Worker:
    worker = _Worker(fn, *args, **kwargs)
    if on_result is not None:
        worker.signals.finished.connect(on_result)
    if on_error is not None:
        worker.signals.error.connect(on_error)
    QThreadPool.globalInstance().start(worker)
    return worker

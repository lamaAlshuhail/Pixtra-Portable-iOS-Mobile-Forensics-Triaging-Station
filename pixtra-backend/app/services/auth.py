from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional


_PBKDF2_ITERATIONS = 600_000
_SESSION_TTL_MINUTES = 60
_LOCKOUT_THRESHOLD = 5
_LOCKOUT_WINDOW_MINUTES = 5


def hash_password(plain: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", plain.encode("utf-8"), salt, _PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, dk_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        expected = bytes.fromhex(dk_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256", plain.encode("utf-8"),
            bytes.fromhex(salt_hex), int(iters),
        )
        return secrets.compare_digest(expected, actual)
    except Exception:
        return False


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _parse_iso(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def create_session(
    db: sqlite3.Connection, examiner_id: int, ip_addr: Optional[str] = None,
) -> dict:
    token = secrets.token_urlsafe(32)
    now = _now()
    expires = now + timedelta(minutes=_SESSION_TTL_MINUTES)
    db.execute(
        """
        INSERT INTO sessions (token, examiner_id, created_at,
                              last_active_at, expires_at, ip_addr)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            token, examiner_id,
            now.isoformat(), now.isoformat(), expires.isoformat(),
            ip_addr,
        ),
    )
    db.commit()
    return {"token": token, "expires_at": expires.isoformat()}


def lookup_session(db: sqlite3.Connection, token: str) -> Optional[dict]:
    if not token:
        return None
    row = db.execute(
        "SELECT * FROM sessions WHERE token = ? LIMIT 1", (token,),
    ).fetchone()
    if not row:
        return None
    expires = _parse_iso(row["expires_at"])
    if expires is None or expires <= _now():
        db.execute("DELETE FROM sessions WHERE token = ?", (token,))
        db.commit()
        return None
    return dict(row)


def touch_session(db: sqlite3.Connection, token: str) -> None:
    now = _now()
    expires = now + timedelta(minutes=_SESSION_TTL_MINUTES)
    db.execute(
        """
        UPDATE sessions
           SET last_active_at = ?, expires_at = ?
         WHERE token = ?
        """,
        (now.isoformat(), expires.isoformat(), token),
    )
    db.commit()


def invalidate_session(db: sqlite3.Connection, token: str) -> None:
    db.execute("DELETE FROM sessions WHERE token = ?", (token,))
    db.commit()


def _cleanup_old_attempts(db: sqlite3.Connection) -> None:
    cutoff = (_now() - timedelta(minutes=_LOCKOUT_WINDOW_MINUTES)).isoformat()
    db.execute(
        "DELETE FROM failed_login_attempts WHERE attempted_at < ?",
        (cutoff,),
    )


def is_locked_out(db: sqlite3.Connection, username: str) -> tuple[bool, int]:
    _cleanup_old_attempts(db)
    cutoff = (_now() - timedelta(minutes=_LOCKOUT_WINDOW_MINUTES)).isoformat()
    rows = db.execute(
        """
        SELECT attempted_at FROM failed_login_attempts
         WHERE username = ? AND attempted_at >= ?
         ORDER BY attempted_at ASC
        """,
        (username, cutoff),
    ).fetchall()
    if len(rows) < _LOCKOUT_THRESHOLD:
        return False, 0
    earliest = _parse_iso(rows[0]["attempted_at"])
    if earliest is None:
        return False, 0
    unlock_at = earliest + timedelta(minutes=_LOCKOUT_WINDOW_MINUTES)
    remaining = unlock_at - _now()
    minutes = max(1, int(remaining.total_seconds() / 60) + 1)
    return True, minutes


def record_failed_attempt(
    db: sqlite3.Connection, username: str, ip_addr: Optional[str] = None,
) -> None:
    db.execute(
        """
        INSERT INTO failed_login_attempts (username, attempted_at, ip_addr)
        VALUES (?, ?, ?)
        """,
        (username, _now_iso(), ip_addr),
    )
    db.commit()


def clear_failed_attempts(db: sqlite3.Connection, username: str) -> None:
    db.execute(
        "DELETE FROM failed_login_attempts WHERE username = ?", (username,),
    )
    db.commit()


_AUTH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS examiners (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT,
    role TEXT NOT NULL CHECK (role IN ('examiner','supervisor','viewer')),
    password_hash TEXT NOT NULL,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    created_by INTEGER,
    last_login_at TEXT,
    password_changed_at TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    examiner_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    last_active_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    ip_addr TEXT,
    FOREIGN KEY (examiner_id) REFERENCES examiners(id)
);

CREATE TABLE IF NOT EXISTS failed_login_attempts (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    attempted_at TEXT NOT NULL,
    ip_addr TEXT
);

CREATE INDEX IF NOT EXISTS idx_failed_attempts_username
    ON failed_login_attempts(username, attempted_at);

CREATE INDEX IF NOT EXISTS idx_sessions_examiner
    ON sessions(examiner_id);
"""


def init_auth_schema(db: sqlite3.Connection) -> None:
    db.executescript(_AUTH_SCHEMA_SQL)
    db.commit()


def bootstrap_default_supervisor(db: sqlite3.Connection) -> Optional[str]:
    row = db.execute("SELECT COUNT(*) AS n FROM examiners").fetchone()
    if row and int(row["n"]) > 0:
        return None
    initial_password = (
        os.environ.get("PIXTRA_BOOTSTRAP_PASSWORD") or secrets.token_urlsafe(12)
    )
    db.execute(
        """
        INSERT INTO examiners (
            username, full_name, email, role, password_hash,
            must_change_password, is_active, created_at, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "admin",
            "Default Administrator",
            None,
            "supervisor",
            hash_password(initial_password),
            1,
            1,
            _now_iso(),
            None,
        ),
    )
    db.commit()
    return initial_password


def public_examiner(row: dict) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "email": row.get("email") if isinstance(row, dict) else row["email"],
        "role": row["role"],
        "must_change_password": bool(row["must_change_password"]),
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"] if "last_login_at" in row.keys() else None,
    }

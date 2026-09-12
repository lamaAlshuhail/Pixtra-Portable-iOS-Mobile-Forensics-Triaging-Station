import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

_ENV_DB = os.environ.get("PIXTRA_DB_PATH")
if _ENV_DB:
    DB_PATH = os.path.abspath(_ENV_DB)
else:
    _PKG_ROOT = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
    _CANDIDATE = os.path.join(_PKG_ROOT, "data", "pixtra.db")
    DB_PATH = (
        _CANDIDATE if os.path.isfile(_CANDIDATE)
        else os.path.abspath("data/pixtra.db")
    )
CASE_STORAGE_ROOT = os.path.abspath(os.environ.get("PIXTRA_CASE_STORAGE", "data/cases"))

_conn: Optional[sqlite3.Connection] = None


def get_db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
    return _conn


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS cases (
            id TEXT PRIMARY KEY,
            case_number TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            examiner TEXT NOT NULL,
            notes TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            device_count INTEGER DEFAULT 0,
            artifact_count INTEGER DEFAULT 0,
            total_size_bytes INTEGER DEFAULT 0,
            integrity_verified INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS devices (
            id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            serial TEXT NOT NULL,
            udid TEXT,
            platform TEXT NOT NULL,
            model TEXT,
            model_name TEXT,
            chipset TEXT,
            os_version TEXT,
            storage_gb REAL,
            added_at TEXT NOT NULL,
            acquisition_id TEXT,
            acquisition_status TEXT
        );

        CREATE TABLE IF NOT EXISTS acquisitions (
            id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL REFERENCES cases(id),
            device_id TEXT NOT NULL REFERENCES devices(id),
            method TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            stage TEXT NOT NULL DEFAULT 'detect',
            started_at TEXT,
            completed_at TEXT,
            output_path TEXT,
            files_extracted INTEGER DEFAULT 0,
            bytes_extracted INTEGER DEFAULT 0,
            hash_manifest_path TEXT,
            error_message TEXT
        );

        CREATE TABLE IF NOT EXISTS custody_log (
            id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL REFERENCES cases(id),
            timestamp TEXT NOT NULL,
            action TEXT NOT NULL,
            examiner TEXT NOT NULL,
            device_id TEXT,
            acquisition_id TEXT,
            details TEXT,
            file_hash TEXT
        );

        CREATE TABLE IF NOT EXISTS hash_manifest (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            acquisition_id TEXT NOT NULL REFERENCES acquisitions(id),
            file_path TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            md5 TEXT,
            sha1 TEXT,
            size_bytes INTEGER NOT NULL,
            hashed_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_devices_case ON devices(case_id);
        CREATE INDEX IF NOT EXISTS idx_acquisitions_case ON acquisitions(case_id);
        CREATE INDEX IF NOT EXISTS idx_custody_case ON custody_log(case_id);
        CREATE INDEX IF NOT EXISTS idx_custody_timestamp ON custody_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_hash_acquisition ON hash_manifest(acquisition_id);
    """)
    db.commit()

    for ddl in (
        "ALTER TABLE cases ADD COLUMN storage_root TEXT",
        "ALTER TABLE acquisitions ADD COLUMN backup_passphrase TEXT",
    ):
        try:
            db.execute(ddl)
            db.commit()
        except sqlite3.OperationalError:
            pass

    from app.services.auth import (
        bootstrap_default_supervisor,
        init_auth_schema,
    )
    init_auth_schema(db)
    initial_password = bootstrap_default_supervisor(db)
    if initial_password:
        print(
            "[auth] Default supervisor 'admin' created. "
            f"Initial password: {initial_password} "
            "(must be changed on first login).",
            flush=True,
        )


def create_case(case: dict) -> dict:
    db = get_db()
    now = datetime.utcnow().isoformat()
    case.setdefault("created_at", now)
    case.setdefault("updated_at", now)
    case.setdefault("status", "active")
    case.setdefault("device_count", 0)
    case.setdefault("artifact_count", 0)
    case.setdefault("total_size_bytes", 0)
    case.setdefault("integrity_verified", 0)
    case.setdefault("storage_root", None)

    db.execute(
        """INSERT INTO cases (id, case_number, name, examiner, notes, status,
           created_at, updated_at, device_count, artifact_count, total_size_bytes,
           integrity_verified, storage_root)
           VALUES (:id, :case_number, :name, :examiner, :notes, :status,
           :created_at, :updated_at, :device_count, :artifact_count, :total_size_bytes,
           :integrity_verified, :storage_root)""",
        case,
    )
    db.commit()

    base = case.get("storage_root") or CASE_STORAGE_ROOT
    case_dir = Path(base) / case["id"]
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "extractions").mkdir(exist_ok=True)
    (case_dir / "reports").mkdir(exist_ok=True)

    return case


def case_dir(case_id: str) -> str:
    db = get_db()
    row = db.execute(
        "SELECT storage_root FROM cases WHERE id = ?", (case_id,)
    ).fetchone()
    base = (row["storage_root"] if row and row["storage_root"] else None) or CASE_STORAGE_ROOT
    return os.path.join(os.path.abspath(base), case_id)


def get_case(case_id: str) -> Optional[dict]:
    db = get_db()
    row = db.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    return dict(row) if row else None


def list_cases(status: Optional[str] = None) -> list[dict]:
    db = get_db()
    if status:
        rows = db.execute(
            "SELECT * FROM cases WHERE status = ? ORDER BY updated_at DESC", (status,)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM cases ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]


def update_case(case_id: str, updates: dict) -> Optional[dict]:
    db = get_db()
    updates["updated_at"] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["id"] = case_id
    db.execute(f"UPDATE cases SET {set_clause} WHERE id = :id", updates)
    db.commit()
    return get_case(case_id)


def delete_case(case_id: str) -> bool:
    db = get_db()
    db.execute(
        """DELETE FROM hash_manifest
            WHERE acquisition_id IN
                  (SELECT id FROM acquisitions WHERE case_id = ?)""",
        (case_id,),
    )
    db.execute("DELETE FROM acquisitions WHERE case_id = ?", (case_id,))
    db.execute("DELETE FROM devices WHERE case_id = ?", (case_id,))
    db.execute("DELETE FROM custody_log WHERE case_id = ?", (case_id,))
    db.execute("DELETE FROM cases WHERE id = ?", (case_id,))
    db.commit()
    return True


def add_device(device: dict) -> dict:
    db = get_db()
    device.setdefault("added_at", datetime.utcnow().isoformat())
    cols = ", ".join(device.keys())
    placeholders = ", ".join(f":{k}" for k in device.keys())
    db.execute(f"INSERT INTO devices ({cols}) VALUES ({placeholders})", device)
    db.execute(
        "UPDATE cases SET device_count = device_count + 1, updated_at = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), device["case_id"]),
    )
    db.commit()
    return device


def get_device(device_id: str) -> Optional[dict]:
    db = get_db()
    row = db.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    return dict(row) if row else None


def list_devices(case_id: str) -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM devices WHERE case_id = ? ORDER BY added_at DESC", (case_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def create_acquisition(acq: dict) -> dict:
    db = get_db()
    cols = ", ".join(acq.keys())
    placeholders = ", ".join(f":{k}" for k in acq.keys())
    db.execute(f"INSERT INTO acquisitions ({cols}) VALUES ({placeholders})", acq)
    db.execute(
        "UPDATE devices SET acquisition_id = ?, acquisition_status = ? WHERE id = ?",
        (acq["id"], acq.get("status", "pending"), acq["device_id"]),
    )
    db.commit()
    return acq


_ACQ_SECRET_COLS = ("backup_passphrase",)


def _public_acq(row) -> dict:
    d = dict(row)
    for k in _ACQ_SECRET_COLS:
        d.pop(k, None)
    return d


def get_acquisition(acq_id: str) -> Optional[dict]:
    db = get_db()
    row = db.execute("SELECT * FROM acquisitions WHERE id = ?", (acq_id,)).fetchone()
    return _public_acq(row) if row else None


def get_acquisition_secret(acq_id: str, key: str) -> Optional[str]:
    if key not in _ACQ_SECRET_COLS:
        raise ValueError(f"Not a secret column: {key}")
    db = get_db()
    row = db.execute(
        f"SELECT {key} FROM acquisitions WHERE id = ?", (acq_id,)
    ).fetchone()
    return row[0] if row else None


def update_acquisition(acq_id: str, updates: dict) -> Optional[dict]:
    db = get_db()
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["id"] = acq_id
    db.execute(f"UPDATE acquisitions SET {set_clause} WHERE id = :id", updates)
    if "status" in updates:
        acq = get_acquisition(acq_id)
        if acq:
            db.execute(
                "UPDATE devices SET acquisition_status = ? WHERE id = ?",
                (updates["status"], acq["device_id"]),
            )
    db.commit()
    return get_acquisition(acq_id)


def list_acquisitions(case_id: str) -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM acquisitions WHERE case_id = ? ORDER BY started_at DESC", (case_id,)
    ).fetchall()
    return [_public_acq(r) for r in rows]


def log_custody(entry: dict) -> dict:
    db = get_db()
    entry.setdefault("timestamp", datetime.utcnow().isoformat())
    cols = ", ".join(entry.keys())
    placeholders = ", ".join(f":{k}" for k in entry.keys())
    db.execute(f"INSERT INTO custody_log ({cols}) VALUES ({placeholders})", entry)
    db.commit()
    return entry


def get_custody_log(case_id: str) -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM custody_log WHERE case_id = ? ORDER BY timestamp ASC", (case_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def insert_file_hash(acquisition_id: str, file_hash: dict):
    db = get_db()
    file_hash["acquisition_id"] = acquisition_id
    file_hash.setdefault("hashed_at", datetime.utcnow().isoformat())
    db.execute(
        """INSERT INTO hash_manifest (acquisition_id, file_path, sha256, md5, sha1, size_bytes, hashed_at)
           VALUES (:acquisition_id, :file_path, :sha256, :md5, :sha1, :size_bytes, :hashed_at)""",
        file_hash,
    )
    db.commit()


def get_hash_manifest(acquisition_id: str) -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM hash_manifest WHERE acquisition_id = ? ORDER BY file_path", (acquisition_id,)
    ).fetchall()
    return [dict(r) for r in rows]

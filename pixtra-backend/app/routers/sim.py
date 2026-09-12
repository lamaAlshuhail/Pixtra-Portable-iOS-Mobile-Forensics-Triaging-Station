from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import sim_reader
from app.services.database import get_case


router = APIRouter()


_CASE_STORAGE_ROOT = os.path.abspath(
    os.environ.get("PIXTRA_CASE_STORAGE", "data/cases")
)


_SIM_SCANS_DDL = """
CREATE TABLE IF NOT EXISTS sim_scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    scan_id TEXT NOT NULL,
    scanned_at TEXT NOT NULL,
    examiner_username TEXT,
    atr TEXT,
    iccid TEXT,
    imsi TEXT,
    mcc TEXT, mnc TEXT, msin TEXT,
    spn TEXT,
    operator_name TEXT,
    country TEXT,
    lai_mcc TEXT, lai_mnc TEXT, lai_lac TEXT,
    pin_required INTEGER DEFAULT 0,
    raw_apdus_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_sim_scans_case ON sim_scans(case_id);
"""


def _artifacts_db_path(case_id: str) -> str:
    from app.services.database import case_dir
    return os.path.join(case_dir(case_id), "artifacts.db")


def _open_artifacts_db(case_id: str, create: bool = False) -> sqlite3.Connection:
    path = _artifacts_db_path(case_id)
    if create:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    elif not os.path.isfile(path):
        raise FileNotFoundError(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SIM_SCANS_DDL)
    conn.commit()
    return conn


class ScanIn(BaseModel):
    case_id: str
    examiner_username: Optional[str] = None


class DeleteScanIn(BaseModel):
    case_id: str


@router.get("/reader/status")
async def reader_status() -> dict:
    return sim_reader.get_reader_status()


@router.post("/scan")
async def scan(body: ScanIn) -> dict:
    case = get_case(body.case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    status = sim_reader.get_reader_status()
    if not status.get("has_reader"):
        raise HTTPException(
            status_code=503,
            detail=status.get("error") or "No smart-card reader detected",
        )
    if not status.get("has_card"):
        raise HTTPException(
            status_code=400, detail="No card in reader",
        )

    try:
        result = sim_reader.scan_sim()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"SIM scan failed: {exc}",
        ) from exc

    scan_id = uuid4().hex[:12]
    scanned_at = datetime.now(tz=timezone.utc).isoformat()

    conn = _open_artifacts_db(body.case_id, create=True)
    try:
        conn.execute(
            """
            INSERT INTO sim_scans (
                case_id, scan_id, scanned_at, examiner_username,
                atr, iccid, imsi, mcc, mnc, msin, spn,
                operator_name, country,
                lai_mcc, lai_mnc, lai_lac,
                pin_required, raw_apdus_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                body.case_id, scan_id, scanned_at, body.examiner_username,
                result.get("atr"),
                result.get("iccid"),
                result.get("imsi"),
                result.get("mcc"),
                result.get("mnc"),
                result.get("msin"),
                result.get("spn"),
                result.get("operator_name"),
                result.get("country"),
                result.get("lai_mcc"),
                result.get("lai_mnc"),
                result.get("lai_lac"),
                1 if result.get("pin_required") else 0,
                json.dumps(result.get("raw_apdus") or [], ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    result["case_id"] = body.case_id
    result["scan_id"] = scan_id
    result["scanned_at"] = scanned_at
    return result


@router.get("/case/{case_id}")
async def list_case_scans(case_id: str) -> dict:
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        conn = _open_artifacts_db(case_id, create=False)
    except FileNotFoundError:
        return {"scans": []}
    try:
        rows = conn.execute(
            """
            SELECT * FROM sim_scans
            WHERE case_id = ?
            ORDER BY scanned_at DESC
            """,
            (case_id,),
        ).fetchall()
    finally:
        conn.close()
    scans: list[dict] = []
    for r in rows:
        d = dict(r)
        try:
            d["raw_apdus"] = json.loads(d.pop("raw_apdus_json") or "[]")
        except (TypeError, ValueError):
            d["raw_apdus"] = []
        d["pin_required"] = bool(d.get("pin_required"))
        scans.append(d)
    return {"scans": scans}


@router.delete("/scan/{scan_id}")
async def delete_scan(scan_id: str, body: DeleteScanIn) -> dict:
    case = get_case(body.case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        conn = _open_artifacts_db(body.case_id, create=False)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Scan not found")
    try:
        cur = conn.execute(
            "DELETE FROM sim_scans WHERE scan_id = ? AND case_id = ?",
            (scan_id, body.case_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Scan not found")
    finally:
        conn.close()
    return {"deleted": True, "scan_id": scan_id}

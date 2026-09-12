import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from uuid import uuid4

from app.models.schemas import (
    CaseCreate, CaseUpdate, Case, CaseStatus,
    CustodyAction, CustodyEntry,
)
from app.routers.auth import require_role
from app.services.database import (
    create_case, get_case, list_cases, update_case, delete_case,
    log_custody, get_custody_log,
)

router = APIRouter()


@router.post("", response_model=dict)
async def create_new_case(
    data: CaseCreate,
    _: dict = Depends(require_role("examiner", "supervisor")),
):
    case_id = uuid4().hex[:12]
    case = {
        "id": case_id,
        "case_number": data.case_number,
        "name": data.name,
        "examiner": data.examiner,
        "notes": data.notes,
        "storage_root": data.storage_root,
    }
    try:
        result = create_case(case)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail=f"Case number {data.case_number!r} already exists",
        )

    log_custody({
        "id": uuid4().hex[:12],
        "case_id": case_id,
        "action": CustodyAction.CASE_CREATED.value,
        "examiner": data.examiner,
        "details": f"Case {data.case_number} created: {data.name}",
    })

    return result


@router.get("", response_model=list[dict])
async def get_cases(status: Optional[str] = None):
    return list_cases(status)


@router.get("/{case_id}", response_model=dict)
async def get_single_case(case_id: str):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    import os
    import sqlite3
    from app.services.database import case_dir
    artifacts_path = os.path.join(case_dir(case_id), "artifacts.db")
    sim_count = 0
    if os.path.isfile(artifacts_path):
        try:
            conn = sqlite3.connect(artifacts_path)
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM sim_scans WHERE case_id = ?",
                    (case_id,),
                ).fetchone()
                sim_count = int(row[0]) if row else 0
            except sqlite3.OperationalError:
                sim_count = 0
            finally:
                conn.close()
        except sqlite3.Error:
            sim_count = 0
    case["sim_scan_count"] = sim_count
    return case


@router.patch("/{case_id}", response_model=dict)
async def update_existing_case(case_id: str, data: CaseUpdate):
    existing = get_case(case_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Case not found")

    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    if "status" in updates:
        updates["status"] = updates["status"].value

    result = update_case(case_id, updates)
    return result


@router.delete("/{case_id}")
async def delete_existing_case(
    case_id: str,
    _: dict = Depends(require_role("supervisor")),
):
    existing = get_case(case_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Case not found")
    delete_case(case_id)
    return {"deleted": True, "case_id": case_id}


@router.get("/{case_id}/custody", response_model=list[dict])
async def get_case_custody_log(case_id: str):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return get_custody_log(case_id)

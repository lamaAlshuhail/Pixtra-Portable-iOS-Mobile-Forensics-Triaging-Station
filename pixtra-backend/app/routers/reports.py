import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from uuid import uuid4
from datetime import datetime

from app.routers.auth import require_role
from app.services.database import get_case, log_custody, DB_PATH
from app.services.database import case_dir as case_dir_for
from app.services.report_engine import generate_report, ReportConfig
from app.models.schemas import CustodyAction

router = APIRouter()

CASE_STORAGE_ROOT = os.path.abspath(os.environ.get("PIXTRA_CASE_STORAGE", "data/cases"))


class ReportRequest(BaseModel):
    title: str = "Forensic Examination Report"
    examiner: str = ""
    organization: str = ""
    format: str = "html"
    sections: list[str] = [
        "case_summary",
        "device_info",
        "methodology",
        "evidence_summary",
        "messages",
        "contacts",
        "calls",
        "timeline",
        "entity_graph",
        "examiner_notes",
        "hash_verification",
        "chain_of_custody",
    ]


@router.post("/{case_id}/generate")
async def generate_case_report(
    case_id: str,
    data: ReportRequest,
    _: dict = Depends(require_role("examiner", "supervisor")),
):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case_dir = case_dir_for(case_id)
    if not os.path.isdir(case_dir):
        os.makedirs(case_dir, exist_ok=True)

    config = ReportConfig(
        title=data.title,
        examiner=data.examiner or case.get("examiner", ""),
        organization=data.organization,
        format=data.format,
        sections=data.sections,
    )

    result = generate_report(
        case_id=case_id,
        case_dir=case_dir,
        db_path=DB_PATH,
        config=config,
    )

    log_custody({
        "id": uuid4().hex[:12],
        "case_id": case_id,
        "action": CustodyAction.REPORT_GENERATED.value,
        "examiner": config.examiner,
        "details": f"Report generated: {result.get('format', 'html')}, "
                   f"sections={len(config.sections)}, "
                   f"time={result.get('generation_time_ms', 0)}ms",
    })

    return result


@router.get("/{case_id}/list")
async def list_reports(case_id: str):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    reports_dir = os.path.join(case_dir_for(case_id), "reports")
    if not os.path.isdir(reports_dir):
        return {"case_id": case_id, "reports": []}

    reports = []
    for fname in sorted(os.listdir(reports_dir), reverse=True):
        fpath = os.path.join(reports_dir, fname)
        if os.path.isfile(fpath):
            ext = os.path.splitext(fname)[1].lower()
            reports.append({
                "filename": fname,
                "format": ext.lstrip("."),
                "size_bytes": os.path.getsize(fpath),
                "created": datetime.fromtimestamp(os.path.getmtime(fpath)).isoformat(),
                "download_url": f"/api/reports/{case_id}/download/{fname}",
            })

    return {"case_id": case_id, "reports": reports}


@router.get("/{case_id}/download/{filename}")
async def download_report(case_id: str, filename: str):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    reports_dir = os.path.join(case_dir_for(case_id), "reports")
    file_path = os.path.join(reports_dir, filename)

    real_reports = os.path.realpath(reports_dir)
    real_file = os.path.realpath(file_path)
    if not real_file.startswith(real_reports + os.sep):
        raise HTTPException(status_code=403, detail="Path traversal blocked")

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Report not found")

    media_type = "text/html" if filename.endswith(".html") else "application/pdf"
    return FileResponse(
        file_path,
        media_type=media_type,
        filename=filename,
    )

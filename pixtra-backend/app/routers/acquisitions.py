import asyncio
import json
import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.models.schemas import (
    AcquisitionStart, AcquisitionStatus, AcquisitionStage,
    AcquisitionProgress, ExtractionMethod, CustodyAction,
)
from app.services.database import (
    create_acquisition, get_acquisition, update_acquisition, list_acquisitions,
    get_case, get_device, log_custody,
    insert_file_hash, get_hash_manifest, get_db,
)
from app.services.acquisition import get_extractor, ProgressCallback
from app.utils.hashing import hash_directory, verify_manifest

logger = logging.getLogger("pixtra.acquisitions")
router = APIRouter()

CASE_STORAGE_ROOT = os.path.abspath(os.environ.get("PIXTRA_CASE_STORAGE", "data/cases"))

_running_extractions: dict[str, object] = {}


@router.post("/start", response_model=dict)
async def start_acquisition(data: AcquisitionStart):
    case = get_case(data.case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    device = get_device(data.device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    acq_id = uuid4().hex[:12]
    case_storage = case.get("storage_root") or CASE_STORAGE_ROOT
    output_dir = data.output_path or os.path.join(
        case_storage, data.case_id, "extractions", acq_id
    )
    os.makedirs(output_dir, exist_ok=True)

    acq = {
        "id": acq_id,
        "case_id": data.case_id,
        "device_id": data.device_id,
        "method": data.method.value,
        "status": AcquisitionStatus.PENDING.value,
        "stage": AcquisitionStage.DETECT.value,
        "started_at": datetime.utcnow().isoformat(),
        "output_path": output_dir,
    }
    create_acquisition(acq)

    log_custody({
        "id": uuid4().hex[:12],
        "case_id": data.case_id,
        "action": CustodyAction.EXTRACTION_STARTED.value,
        "examiner": case["examiner"],
        "device_id": data.device_id,
        "acquisition_id": acq_id,
        "details": (
            f"Extraction started: method={data.method.value}, "
            f"device={device.get('model_name', device['serial'])}"
        ),
    })

    asyncio.create_task(_run_extraction(acq_id, data, device, output_dir, case))

    return {
        "acquisition_id": acq_id,
        "status": "pending",
        "ws_url": f"/api/acquisitions/ws/{acq_id}",
    }


async def _run_extraction(
    acq_id: str,
    data: AcquisitionStart,
    device: dict,
    output_dir: str,
    case: dict,
):
    progress_log: list[dict] = []

    def on_progress(p: AcquisitionProgress):
        progress_log.append(p.model_dump())
        update_acquisition(acq_id, {
            "status": p.status.value,
            "stage": p.stage.value,
            "files_extracted": p.files_extracted,
            "bytes_extracted": p.bytes_extracted,
        })
        _broadcast_progress(acq_id, p)

    try:
        extractor = get_extractor(
            method=data.method,
            acquisition_id=acq_id,
            device_serial=device["serial"],
            output_dir=output_dir,
            progress_cb=on_progress,
        )
        _running_extractions[acq_id] = extractor

        result = await extractor.extract()

        if result["success"]:
            logger.info(f"Generating hash manifest for {acq_id}...")
            hashes = hash_directory(result["output_path"])
            for h in hashes:
                if "error" not in h:
                    insert_file_hash(acq_id, h)

            manifest_path = os.path.join(output_dir, "hash_manifest.json")
            with open(manifest_path, "w") as f:
                json.dump(hashes, f, indent=2)

            update_acquisition(acq_id, {
                "status": AcquisitionStatus.COMPLETE.value,
                "stage": AcquisitionStage.COMPLETE.value,
                "completed_at": datetime.utcnow().isoformat(),
                "files_extracted": result["files_extracted"],
                "bytes_extracted": result["bytes_extracted"],
                "hash_manifest_path": manifest_path,
                "output_path": result["output_path"],
            })

            log_custody({
                "id": uuid4().hex[:12],
                "case_id": data.case_id,
                "action": CustodyAction.EXTRACTION_COMPLETE.value,
                "examiner": case["examiner"],
                "device_id": data.device_id,
                "acquisition_id": acq_id,
                "details": (
                    f"Extraction complete: {result['files_extracted']} files, "
                    f"{result['bytes_extracted']} bytes"
                ),
            })
        else:
            update_acquisition(acq_id, {
                "status": AcquisitionStatus.FAILED.value,
                "error_message": result.get("error", "Unknown error"),
                "completed_at": datetime.utcnow().isoformat(),
            })

            log_custody({
                "id": uuid4().hex[:12],
                "case_id": data.case_id,
                "action": CustodyAction.EXTRACTION_FAILED.value,
                "examiner": case["examiner"],
                "device_id": data.device_id,
                "acquisition_id": acq_id,
                "details": f"Extraction failed: {result.get('error', 'Unknown')}",
            })

    except Exception as e:
        logger.error(f"Extraction {acq_id} failed with exception: {e}")
        update_acquisition(acq_id, {
            "status": AcquisitionStatus.FAILED.value,
            "error_message": str(e),
        })
    finally:
        _running_extractions.pop(acq_id, None)


_ws_subscribers: dict[str, list[WebSocket]] = {}


def _broadcast_progress(acq_id: str, progress: AcquisitionProgress):
    sockets = _ws_subscribers.get(acq_id, [])
    dead = []
    for ws in sockets:
        try:
            asyncio.create_task(ws.send_json(progress.model_dump()))
        except Exception:
            dead.append(ws)
    for ws in dead:
        sockets.remove(ws)


@router.websocket("/ws/{acquisition_id}")
async def acquisition_progress_ws(websocket: WebSocket, acquisition_id: str):
    await websocket.accept()

    if acquisition_id not in _ws_subscribers:
        _ws_subscribers[acquisition_id] = []
    _ws_subscribers[acquisition_id].append(websocket)

    try:
        acq = get_acquisition(acquisition_id)
        if acq:
            await websocket.send_json({
                "acquisition_id": acquisition_id,
                "status": acq["status"],
                "stage": acq.get("stage", "detect"),
                "files_extracted": acq.get("files_extracted", 0),
                "bytes_extracted": acq.get("bytes_extracted", 0),
            })

        while True:
            data = await websocket.receive_text()
            if data == "cancel":
                extractor = _running_extractions.get(acquisition_id)
                if extractor:
                    extractor.cancel()
                    await websocket.send_json({"status": "cancelling"})

    except WebSocketDisconnect:
        pass
    finally:
        subs = _ws_subscribers.get(acquisition_id, [])
        if websocket in subs:
            subs.remove(websocket)


@router.get("/find-backups")
async def find_itunes_backups():
    import platform as plat

    backup_locations = []
    system = plat.system()

    if system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        paths = [
            os.path.join(appdata, "Apple Computer", "MobileSync", "Backup"),
            os.path.join(appdata, "Apple", "MobileSync", "Backup"),
            os.path.join(os.environ.get("USERPROFILE", ""), "Apple", "MobileSync", "Backup"),
        ]
    elif system == "Darwin":
        home = os.path.expanduser("~")
        paths = [
            os.path.join(home, "Library", "Application Support", "MobileSync", "Backup"),
        ]
    else:
        home = os.path.expanduser("~")
        paths = [
            os.path.join(home, ".config", "pymobiledevice3", "backups"),
            os.path.join(home, "pymobiledevice3_backups"),
        ]

    backups = []
    for base_path in paths:
        if not os.path.isdir(base_path):
            continue
        for entry in os.scandir(base_path):
            if entry.is_dir():
                info_plist = os.path.join(entry.path, "Info.plist")
                manifest_db = os.path.join(entry.path, "Manifest.db")

                file_count = 0
                total_size = 0
                for root, dirs, files in os.walk(entry.path):
                    file_count += len(files)
                    for f in files:
                        try:
                            total_size += os.path.getsize(os.path.join(root, f))
                        except OSError:
                            pass

                backup_info = {
                    "path": entry.path,
                    "udid": entry.name,
                    "has_info_plist": os.path.exists(info_plist),
                    "has_manifest_db": os.path.exists(manifest_db),
                    "file_count": file_count,
                    "size_bytes": total_size,
                    "size_human": f"{total_size / (1024**3):.1f} GB" if total_size > 1e9 else f"{total_size / (1024**2):.0f} MB",
                    "modified": datetime.fromtimestamp(entry.stat().st_mtime).isoformat(),
                }

                if os.path.exists(info_plist):
                    try:
                        import plistlib
                        with open(info_plist, "rb") as f:
                            plist = plistlib.load(f)
                        backup_info["device_name"] = plist.get("Device Name", "Unknown")
                        backup_info["product_type"] = plist.get("Product Type", "")
                        backup_info["product_version"] = plist.get("Product Version", "")
                        backup_info["serial_number"] = plist.get("Serial Number", "")
                        backup_info["last_backup_date"] = str(plist.get("Last Backup Date", ""))
                    except Exception:
                        pass

                backups.append(backup_info)

    backups.sort(key=lambda b: b.get("modified", ""), reverse=True)

    return {
        "system": system,
        "searched_paths": paths,
        "backups": backups,
        "count": len(backups),
    }


@router.post("/import")
async def import_image(
    case_id: str,
    source_path: str,
    platform: str = "ios",
    label: str = "Imported image",
):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not os.path.exists(source_path):
        raise HTTPException(status_code=400, detail=f"Path not found: {source_path}")

    resolved_path = source_path
    if os.path.isdir(source_path):
        entries = os.listdir(source_path)

        for entry in entries:
            full = os.path.join(source_path, entry)
            if os.path.isdir(full) and (len(entry) == 40 or entry.startswith("0000")):
                logger.info(f"Auto-detected UDID subfolder: {entry}")
                resolved_path = full
                break

        snapshot = os.path.join(resolved_path, "Snapshot")
        if os.path.isdir(snapshot):
            snapshot_files = sum(1 for _ in os.scandir(snapshot) if _.is_dir())
            if snapshot_files > 10:
                logger.info(f"Auto-detected Snapshot subfolder with {snapshot_files} hash dirs")
                resolved_path = snapshot

        if os.path.exists(os.path.join(resolved_path, "Manifest.db")):
            logger.info("Found Manifest.db - iTunes backup format")

    logger.info(f"Import resolved path: {source_path} → {resolved_path}")

    acq_id = uuid4().hex[:12]
    device_id = uuid4().hex[:12]

    total_files = 0
    total_bytes = 0
    if os.path.isdir(resolved_path):
        for root, dirs, files in os.walk(resolved_path):
            for f in files:
                total_files += 1
                try:
                    total_bytes += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    elif os.path.isfile(resolved_path):
        total_files = 1
        total_bytes = os.path.getsize(resolved_path)

    from app.services.database import add_device
    add_device({
        "id": device_id,
        "case_id": case_id,
        "serial": f"imported-{acq_id}",
        "platform": platform,
        "model_name": label,
        "chipset": "Unknown (imported)",
    })

    acq = {
        "id": acq_id,
        "case_id": case_id,
        "device_id": device_id,
        "method": "import_image",
        "status": "complete",
        "stage": "complete",
        "started_at": datetime.utcnow().isoformat(),
        "completed_at": datetime.utcnow().isoformat(),
        "output_path": resolved_path,
        "files_extracted": total_files,
        "bytes_extracted": total_bytes,
    }
    create_acquisition(acq)
    update_acquisition(acq_id, {"status": "complete", "stage": "complete"})

    log_custody({
        "id": uuid4().hex[:12],
        "case_id": case_id,
        "action": CustodyAction.EXTRACTION_COMPLETE.value,
        "examiner": case["examiner"],
        "device_id": device_id,
        "acquisition_id": acq_id,
        "details": f"Imported image: {source_path} ({total_files} files, {total_bytes} bytes)",
    })

    from app.services.database import update_case
    update_case(case_id, {
        "total_size_bytes": (case.get("total_size_bytes") or 0) + total_bytes,
        "artifact_count": (case.get("artifact_count") or 0) + total_files,
    })

    return {
        "acquisition_id": acq_id,
        "device_id": device_id,
        "files": total_files,
        "bytes": total_bytes,
        "source_path": source_path,
        "message": f"Imported successfully. Now call POST /api/analysis/parse/{acq_id} to parse the evidence.",
    }


@router.post("/quick-backup")
async def quick_backup(case_id: str, udid: str = None, full: bool = True):
    if not full:
        raise HTTPException(
            status_code=400,
            detail=(
                "full=False is not supported - partial backups omit forensic "
                "evidence (keychain, sandboxed app data, etc.). Re-call with "
                "full=true."
            ),
        )

    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    acq_id = uuid4().hex[:12]
    device_id = uuid4().hex[:12]
    case_storage = case.get("storage_root") or CASE_STORAGE_ROOT
    output_dir = os.path.abspath(os.path.join(case_storage, case_id, "extractions", acq_id))
    os.makedirs(output_dir, exist_ok=True)

    from app.services.database import add_device
    add_device({
        "id": device_id,
        "case_id": case_id,
        "serial": udid or "unknown",
        "udid": udid,
        "platform": "ios",
        "model_name": "iPhone (backing up...)",
    })

    acq = {
        "id": acq_id,
        "case_id": case_id,
        "device_id": device_id,
        "method": "logical_backup",
        "status": "in_progress",
        "stage": "rsync",
        "started_at": datetime.utcnow().isoformat(),
        "output_path": output_dir,
    }
    create_acquisition(acq)

    log_custody({
        "id": uuid4().hex[:12],
        "case_id": case_id,
        "action": CustodyAction.EXTRACTION_STARTED.value,
        "examiner": case["examiner"],
        "device_id": device_id,
        "acquisition_id": acq_id,
        "details": "Full encrypted logical backup started via pymobiledevice3 + iphone_backup_decrypt",
    })

    asyncio.create_task(_run_quick_backup(acq_id, device_id, case_id, output_dir, udid, case))

    return {
        "acquisition_id": acq_id,
        "device_id": device_id,
        "status": "in_progress",
        "full": True,
        "message": "Full encrypted backup started. Takes 10–30 minutes depending on device size.",
    }


@router.post("/cancel-backup/{acquisition_id}")
async def cancel_backup(acquisition_id: str):
    extractor = _running_extractions.get(acquisition_id)
    if not extractor:
        raise HTTPException(status_code=404, detail="No running backup found")
    extractor.cancel()
    update_acquisition(acquisition_id, {
        "status": AcquisitionStatus.CANCELLED.value,
    })
    return {"cancelled": True}


async def _run_quick_backup(acq_id, device_id, case_id, output_dir, udid, case):
    def on_progress(p: AcquisitionProgress):
        update_acquisition(acq_id, {
            "status": p.status.value,
            "stage": p.stage.value,
            "files_extracted": p.files_extracted,
            "bytes_extracted": p.bytes_extracted,
        })
        _broadcast_progress(acq_id, p)

    try:
        extractor = get_extractor(
            method=ExtractionMethod.LOGICAL_BACKUP,
            acquisition_id=acq_id,
            device_serial=udid or "unknown",
            output_dir=output_dir,
            progress_cb=on_progress,
        )
        _running_extractions[acq_id] = extractor

        result = await extractor.extract()

        if result["success"]:
            logger.info(f"Generating hash manifest for {acq_id}...")
            hashes = hash_directory(result["output_path"])
            for h in hashes:
                if "error" not in h:
                    insert_file_hash(acq_id, h)

            manifest_path = os.path.join(output_dir, "hash_manifest.json")
            with open(manifest_path, "w") as f:
                json.dump(hashes, f, indent=2)

            update_acquisition(acq_id, {
                "status": AcquisitionStatus.COMPLETE.value,
                "stage": AcquisitionStage.COMPLETE.value,
                "completed_at": datetime.utcnow().isoformat(),
                "files_extracted": result["files_extracted"],
                "bytes_extracted": result["bytes_extracted"],
                "hash_manifest_path": manifest_path,
                "output_path": result["output_path"],
            })

            from app.services.database import get_db
            db = get_db()
            db.execute(
                "UPDATE devices SET model_name = ? WHERE id = ?",
                (f"iPhone (backup - {result['files_extracted']} files)", device_id),
            )
            db.commit()

            log_custody({
                "id": uuid4().hex[:12],
                "case_id": case_id,
                "action": CustodyAction.EXTRACTION_COMPLETE.value,
                "examiner": case["examiner"],
                "device_id": device_id,
                "acquisition_id": acq_id,
                "details": (
                    f"Backup complete: {result['files_extracted']} files, "
                    f"{result['bytes_extracted']} bytes"
                ),
            })
            logger.info(
                f"quick-backup {acq_id} complete: {result['files_extracted']} files, "
                f"{result['bytes_extracted']/(1024**2):.1f} MB"
            )
        else:
            update_acquisition(acq_id, {
                "status": AcquisitionStatus.FAILED.value,
                "error_message": result.get("error", "Unknown error"),
                "completed_at": datetime.utcnow().isoformat(),
            })
            log_custody({
                "id": uuid4().hex[:12],
                "case_id": case_id,
                "action": CustodyAction.EXTRACTION_FAILED.value,
                "examiner": case["examiner"],
                "device_id": device_id,
                "acquisition_id": acq_id,
                "details": f"Backup failed: {result.get('error', 'Unknown')}",
            })
            logger.error(f"quick-backup {acq_id} failed: {result.get('error')}")

    except Exception as e:
        logger.error(f"quick-backup {acq_id} exception: {e}", exc_info=True)
        update_acquisition(acq_id, {
            "status": AcquisitionStatus.FAILED.value,
            "error_message": str(e),
        })
    finally:
        _running_extractions.pop(acq_id, None)


@router.get("/{acquisition_id}", response_model=dict)
async def get_acquisition_status(acquisition_id: str):
    acq = get_acquisition(acquisition_id)
    if not acq:
        raise HTTPException(status_code=404, detail="Acquisition not found")
    return acq


@router.get("/case/{case_id}", response_model=list[dict])
async def list_case_acquisitions(case_id: str):
    return list_acquisitions(case_id)


@router.post("/{acquisition_id}/cancel")
async def cancel_acquisition(acquisition_id: str):
    extractor = _running_extractions.get(acquisition_id)
    if not extractor:
        raise HTTPException(status_code=404, detail="No running extraction found")
    extractor.cancel()
    update_acquisition(acquisition_id, {
        "status": AcquisitionStatus.CANCELLED.value,
    })
    return {"cancelled": True}


@router.get("/{acquisition_id}/hashes", response_model=list[dict])
async def get_acquisition_hashes(acquisition_id: str):
    acq = get_acquisition(acquisition_id)
    if not acq:
        raise HTTPException(status_code=404, detail="Acquisition not found")
    return get_hash_manifest(acquisition_id)


@router.post("/{acquisition_id}/verify")
async def verify_acquisition_hashes(acquisition_id: str):
    acq = get_acquisition(acquisition_id)
    if not acq:
        raise HTTPException(status_code=404, detail="Acquisition not found")
    if not acq.get("output_path"):
        raise HTTPException(status_code=400, detail="No output path for this acquisition")

    manifest = get_hash_manifest(acquisition_id)
    if not manifest:
        raise HTTPException(status_code=400, detail="No hash manifest found")

    results = verify_manifest(manifest, acq["output_path"])

    all_match = all(r["match"] for r in results)
    mismatches = [r for r in results if not r["match"]]

    case_id = acq["case_id"]
    case = get_case(case_id)
    action = CustodyAction.HASH_VERIFIED if all_match else CustodyAction.HASH_MISMATCH
    log_custody({
        "id": uuid4().hex[:12],
        "case_id": case_id,
        "action": action.value,
        "examiner": case["examiner"] if case else "system",
        "acquisition_id": acquisition_id,
        "details": (
            f"Hash verification: {len(results)} files checked, "
            f"{len(mismatches)} mismatches"
        ),
    })

    return {
        "verified": all_match,
        "total_files": len(results),
        "matches": len(results) - len(mismatches),
        "mismatches": len(mismatches),
        "mismatch_details": mismatches[:50],
    }


@router.post("/{acquisition_id}/reverify-hashes")
async def reverify_acquisition_hashes(acquisition_id: str):
    acq = get_acquisition(acquisition_id)
    if not acq:
        raise HTTPException(status_code=404, detail="Acquisition not found")
    output_path = acq.get("output_path")
    if not output_path:
        raise HTTPException(status_code=400, detail="No output path for this acquisition")
    if not os.path.isdir(output_path):
        raise HTTPException(
            status_code=400,
            detail=f"Output path does not exist on disk: {output_path}",
        )

    prior = {entry["file_path"]: entry for entry in get_hash_manifest(acquisition_id)}
    fresh_list = hash_directory(output_path)
    fresh = {h["file_path"]: h for h in fresh_list if "error" not in h}

    verified = 0
    mismatched = 0
    missing = 0
    mismatch_details: list[dict] = []

    for file_path, prior_row in prior.items():
        if file_path not in fresh:
            missing += 1
            mismatch_details.append({
                "file_path": file_path,
                "status": "missing",
                "expected_sha256": prior_row.get("sha256"),
                "actual_sha256": None,
            })
        elif fresh[file_path].get("sha256") == prior_row.get("sha256"):
            verified += 1
        else:
            mismatched += 1
            mismatch_details.append({
                "file_path": file_path,
                "status": "mismatch",
                "expected_sha256": prior_row.get("sha256"),
                "actual_sha256": fresh[file_path].get("sha256"),
            })

    db = get_db()
    db.execute(
        "DELETE FROM hash_manifest WHERE acquisition_id = ?", (acquisition_id,)
    )
    db.commit()
    for h in fresh_list:
        if "error" not in h:
            insert_file_hash(acquisition_id, h)

    case_id = acq["case_id"]
    case = get_case(case_id)
    all_ok = mismatched == 0 and missing == 0
    action = CustodyAction.HASH_VERIFIED if all_ok else CustodyAction.HASH_MISMATCH
    log_custody({
        "id": uuid4().hex[:12],
        "case_id": case_id,
        "action": action.value,
        "examiner": case["examiner"] if case else "system",
        "acquisition_id": acquisition_id,
        "details": (
            f"Re-verify: verified={verified}, mismatched={mismatched}, "
            f"missing={missing}"
        ),
    })

    return {
        "verified": verified,
        "mismatched": mismatched,
        "missing": missing,
        "mismatch_details": mismatch_details[:50],
    }

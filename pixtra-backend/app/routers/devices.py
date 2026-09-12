from fastapi import APIRouter, HTTPException
from typing import Optional
from uuid import uuid4

from app.models.schemas import (
    DetectedDevice, CaseDevice, DevicePlatform,
    CustodyAction,
)
from app.services.detection import detect_all_devices, detect_ios_devices, detect_android_devices
from app.services.device_profiles import lookup_profile, search_profiles, list_all_profiles, get_profile_count
from app.services.database import (
    add_device, get_device, list_devices, get_case,
    log_custody,
)

router = APIRouter()


@router.get("/detect", response_model=list[DetectedDevice])
async def detect_connected_devices():
    return await detect_all_devices()


@router.get("/detect/ios", response_model=list[DetectedDevice])
async def detect_ios():
    return await detect_ios_devices()


@router.get("/detect/android", response_model=list[DetectedDevice])
async def detect_android():
    return detect_android_devices()


@router.post("/add-to-case", response_model=dict)
async def add_device_to_case(
    case_id: str,
    device: DetectedDevice,
):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    device_id = uuid4().hex[:12]
    device_data = {
        "id": device_id,
        "case_id": case_id,
        "serial": device.serial,
        "udid": device.udid,
        "platform": device.platform.value,
        "model": device.model,
        "model_name": device.model_name,
        "chipset": device.chipset,
        "os_version": device.os_version,
        "storage_gb": device.storage_gb,
    }
    result = add_device(device_data)

    log_custody({
        "id": uuid4().hex[:12],
        "case_id": case_id,
        "action": CustodyAction.DEVICE_CONNECTED.value,
        "examiner": case["examiner"],
        "device_id": device_id,
        "details": (
            f"Device added: {device.model_name or device.model or 'Unknown'} "
            f"(serial: {device.serial})"
        ),
    })

    return result


@router.get("/case/{case_id}", response_model=list[dict])
async def list_case_devices(case_id: str):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return list_devices(case_id)


@router.get("/{device_id}", response_model=dict)
async def get_single_device(device_id: str):
    device = get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.get("/profiles/count")
async def profile_count():
    return {"count": get_profile_count()}


@router.get("/profiles/search")
async def search_device_profiles(q: str, platform: Optional[str] = None):
    results = search_profiles(q, platform)
    return [p.model_dump() for p in results]


@router.get("/profiles/list")
async def list_device_profiles(platform: Optional[str] = None):
    results = list_all_profiles(platform)
    return [p.model_dump() for p in results]

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from uuid import uuid4


class CaseStatus(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"


class DevicePlatform(str, enum.Enum):
    IOS = "ios"
    ANDROID = "android"
    OTHER = "other"


class ExtractionMethod(str, enum.Enum):
    LOGICAL_BACKUP = "logical_backup"
    ADVANCED_LOGICAL = "advanced_logical"
    CHECKM8_FILESYSTEM = "checkm8_filesystem"
    CHECKM8_PHYSICAL = "checkm8_physical"
    AGENT_BASED = "agent_based"
    ADB_LOGICAL = "adb_logical"
    ADB_BACKUP = "adb_backup"
    ADB_ROOT = "adb_root"
    MTK_BYPASS = "mtk_bypass"
    EDL_EXTRACTION = "edl_extraction"
    LG_LAF = "lg_laf"
    IMPORT_IMAGE = "import_image"


class ExtractionCapability(str, enum.Enum):
    LOGICAL = "logical"
    FILESYSTEM = "filesystem"
    PHYSICAL = "physical"
    CHECKM8 = "checkm8"
    MTK_BYPASS = "mtk_bypass"
    EDL = "edl"


class AcquisitionStatus(str, enum.Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    HASHING = "hashing"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AcquisitionStage(str, enum.Enum):
    DETECT = "detect"
    DFU = "dfu"
    EXPLOIT = "exploit"
    SSH = "ssh"
    RSYNC = "rsync"
    KEYCHAIN = "keychain"
    HASH = "hash"
    VERIFY = "verify"
    COMPLETE = "complete"


class CustodyAction(str, enum.Enum):
    CASE_CREATED = "case_created"
    DEVICE_CONNECTED = "device_connected"
    DEVICE_DETECTED = "device_detected"
    EXTRACTION_STARTED = "extraction_started"
    EXTRACTION_PAUSED = "extraction_paused"
    EXTRACTION_RESUMED = "extraction_resumed"
    EXTRACTION_COMPLETE = "extraction_complete"
    EXTRACTION_FAILED = "extraction_failed"
    EXTRACTION_CANCELLED = "extraction_cancelled"
    HASH_VERIFIED = "hash_verified"
    HASH_MISMATCH = "hash_mismatch"
    EVIDENCE_ACCESSED = "evidence_accessed"
    REPORT_GENERATED = "report_generated"
    NOTE_CREATED = "note_created"
    CASE_CLOSED = "case_closed"


class CaseCreate(BaseModel):
    case_number: str = Field(..., description="Case identifier (e.g. C-0042)")
    name: str = Field(..., description="Case name/description")
    examiner: str = Field(..., description="Examiner name and credentials")
    notes: Optional[str] = None
    storage_root: Optional[str] = Field(
        None,
        description="External-drive mount used as the base path for this case's "
                    "extractions. Falls back to PIXTRA_CASE_STORAGE when null.",
    )


class CaseUpdate(BaseModel):
    name: Optional[str] = None
    examiner: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[CaseStatus] = None
    storage_root: Optional[str] = None


class Case(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    case_number: str
    name: str
    examiner: str
    notes: Optional[str] = None
    status: CaseStatus = CaseStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    device_count: int = 0
    artifact_count: int = 0
    total_size_bytes: int = 0
    integrity_verified: bool = False
    storage_root: Optional[str] = None


class DetectedDevice(BaseModel):
    serial: str
    udid: Optional[str] = None
    platform: DevicePlatform
    model: Optional[str] = None
    model_name: Optional[str] = None
    chipset: Optional[str] = None
    os_version: Optional[str] = None
    storage_gb: Optional[float] = None
    battery_percent: Optional[int] = None
    is_locked: Optional[bool] = None
    is_passcode_set: Optional[bool] = None
    usb_debug_enabled: Optional[bool] = None
    capabilities: list[ExtractionCapability] = []
    recommended_method: Optional[ExtractionMethod] = None


class CaseDevice(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    case_id: str
    serial: str
    udid: Optional[str] = None
    platform: DevicePlatform
    model: Optional[str] = None
    model_name: Optional[str] = None
    chipset: Optional[str] = None
    os_version: Optional[str] = None
    storage_gb: Optional[float] = None
    added_at: datetime = Field(default_factory=datetime.utcnow)
    acquisition_id: Optional[str] = None
    acquisition_status: Optional[AcquisitionStatus] = None


class AcquisitionStart(BaseModel):
    case_id: str
    device_id: str
    method: ExtractionMethod
    output_path: Optional[str] = None


class AcquisitionProgress(BaseModel):
    acquisition_id: str
    status: AcquisitionStatus
    stage: AcquisitionStage
    progress_percent: float = 0.0
    files_extracted: int = 0
    bytes_extracted: int = 0
    current_file: Optional[str] = None
    elapsed_seconds: float = 0.0
    estimated_remaining_seconds: Optional[float] = None
    message: Optional[str] = None


class Acquisition(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    case_id: str
    device_id: str
    method: ExtractionMethod
    status: AcquisitionStatus = AcquisitionStatus.PENDING
    stage: AcquisitionStage = AcquisitionStage.DETECT
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    output_path: Optional[str] = None
    files_extracted: int = 0
    bytes_extracted: int = 0
    hash_manifest_path: Optional[str] = None
    error_message: Optional[str] = None


class CustodyEntry(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    case_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    action: CustodyAction
    examiner: str
    device_id: Optional[str] = None
    acquisition_id: Optional[str] = None
    details: Optional[str] = None
    file_hash: Optional[str] = None


class FileHash(BaseModel):
    file_path: str
    sha256: str
    md5: Optional[str] = None
    sha1: Optional[str] = None
    size_bytes: int
    hashed_at: datetime = Field(default_factory=datetime.utcnow)


class HashManifest(BaseModel):
    acquisition_id: str
    case_id: str
    device_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    total_files: int
    total_bytes: int
    files: list[FileHash] = []


class VerificationResult(BaseModel):
    file_path: str
    expected_sha256: str
    actual_sha256: str
    match: bool
    verified_at: datetime = Field(default_factory=datetime.utcnow)


class DeviceProfile(BaseModel):
    model_id: str
    model_name: str
    vendor: str
    platform: DevicePlatform
    chipset: str
    chip_code: Optional[str] = None
    os_range: Optional[str] = None
    capabilities: list[ExtractionCapability] = []
    recommended_method: Optional[ExtractionMethod] = None
    notes: Optional[str] = None

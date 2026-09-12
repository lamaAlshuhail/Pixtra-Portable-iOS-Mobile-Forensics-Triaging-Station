import asyncio
import json
import logging
import os
import secrets
import shutil
import subprocess
import sys
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from app.models.schemas import (
    AcquisitionStatus,
    AcquisitionStage,
    AcquisitionProgress,
    ExtractionMethod,
)
from app.utils.hashing import hash_directory

logger = logging.getLogger("pixtra.acquisition")

ProgressCallback = Callable[[AcquisitionProgress], None]


class BaseExtractor(ABC):

    def __init__(
        self,
        acquisition_id: str,
        device_serial: str,
        output_dir: str,
        progress_cb: Optional[ProgressCallback] = None,
    ):
        self.acquisition_id = acquisition_id
        self.device_serial = device_serial
        self.output_dir = output_dir
        self.progress_cb = progress_cb
        self.files_extracted = 0
        self.bytes_extracted = 0
        self.start_time = 0.0
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _report(
        self,
        status: AcquisitionStatus,
        stage: AcquisitionStage,
        progress: float = 0.0,
        message: str = "",
        current_file: str = None,
    ):
        if self.progress_cb:
            elapsed = time.time() - self.start_time if self.start_time else 0
            self.progress_cb(AcquisitionProgress(
                acquisition_id=self.acquisition_id,
                status=status,
                stage=stage,
                progress_percent=min(progress, 100.0),
                files_extracted=self.files_extracted,
                bytes_extracted=self.bytes_extracted,
                current_file=current_file,
                elapsed_seconds=elapsed,
                message=message,
            ))

    @abstractmethod
    async def extract(self) -> dict:
        pass


FORENSIC_DOMAINS = [
    "HomeDomain",
    "AppDomainGroup-group.net.whatsapp.WhatsApp.shared",
    "AppDomain-net.whatsapp.WhatsApp",
    "AppDomain-com.burbn.instagram",
    "KeychainDomain",
    "WirelessDomain",
    "RootDomain",
    "MediaDomain",
    "CameraRollDomain",
]


def resolve_backup_passphrase(acquisition_id: str, device_serial: str) -> str:
    env = os.environ.get("PIXTRA_BACKUP_PASSPHRASE")
    if env:
        passphrase = env
    else:
        passphrase = None
        try:
            from app.services.database import get_db
            db = get_db()
            ids = {device_serial} if device_serial else set()
            dev = db.execute(
                """SELECT d.udid, d.serial FROM acquisitions a
                     JOIN devices d ON d.id = a.device_id
                    WHERE a.id = ?""",
                (acquisition_id,),
            ).fetchone()
            if dev:
                ids.update(v for v in (dev[0], dev[1]) if v and v != "unknown")
            ids.discard("unknown")
            if ids:
                marks = ",".join("?" * len(ids))
                row = db.execute(
                    f"""
                    SELECT a.backup_passphrase
                      FROM acquisitions a
                      JOIN devices d ON d.id = a.device_id
                     WHERE a.backup_passphrase IS NOT NULL
                       AND a.id != ?
                       AND (d.udid IN ({marks}) OR d.serial IN ({marks}))
                     ORDER BY a.started_at DESC
                     LIMIT 1
                    """,
                    (acquisition_id, *ids, *ids),
                ).fetchone()
                if row and row[0]:
                    passphrase = row[0]
        except Exception as e:
            logger.warning(f"Could not look up prior backup passphrase: {e}")
        if not passphrase:
            passphrase = secrets.token_urlsafe(24)

    try:
        from app.services.database import update_acquisition
        update_acquisition(acquisition_id, {"backup_passphrase": passphrase})
    except Exception as e:
        logger.warning(f"Could not persist backup passphrase: {e}")
    return passphrase


class IOSLogicalExtractor(BaseExtractor):

    async def extract(self) -> dict:
        self.start_time = time.time()
        backup_dir = os.path.join(self.output_dir, "ios_backup")
        decrypt_parent = os.environ.get("PIXTRA_DECRYPT_DIR")
        if decrypt_parent:
            decrypted_dir = os.path.join(decrypt_parent, self.acquisition_id)
        else:
            decrypted_dir = os.path.join(self.output_dir, "ios_backup_decrypted")
        os.makedirs(backup_dir, exist_ok=True)
        os.makedirs(decrypted_dir, exist_ok=True)

        passphrase = resolve_backup_passphrase(
            self.acquisition_id, self.device_serial
        )

        self._report(AcquisitionStatus.PREPARING, AcquisitionStage.DETECT,
                     message="Connecting to iOS device...")

        try:
            self._report(AcquisitionStatus.PREPARING, AcquisitionStage.DETECT,
                         progress=2.0, message="Enabling backup encryption...")

            enc_proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pymobiledevice3", "backup2", "encryption",
                "on", passphrase,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            enc_stdout_b, enc_stderr_b = await enc_proc.communicate()
            enc_stderr = enc_stderr_b.decode("utf-8", errors="replace")
            enc_stdout = enc_stdout_b.decode("utf-8", errors="replace")
            enc_combined = (enc_stdout + "\n" + enc_stderr).lower()
            already_on = (
                "encryption already on" in enc_combined
                or "already enabled" in enc_combined
            )

            if enc_proc.returncode != 0 and not already_on:
                error_msg = (
                    "Could not enable iOS backup encryption. A different passphrase "
                    "may already be set on this device. To clear it, on the iPhone go to "
                    "Settings → General → Transfer or Reset iPhone → Reset → Reset All Settings, "
                    "then retry the acquisition. "
                    f"(pymobiledevice3 stderr: {enc_stderr.strip()[:500]})"
                )
                logger.error(error_msg)
                return {"success": False, "error": error_msg,
                        "files_extracted": 0, "bytes_extracted": 0,
                        "output_path": backup_dir}

            if already_on:
                logger.info("Backup encryption already enabled - proceeding.")
            else:
                logger.info("Backup encryption enabled with examiner passphrase.")

            try:
                from app.services.database import get_acquisition, get_case, log_custody
                from app.models.schemas import CustodyAction
                acq = get_acquisition(self.acquisition_id) or {}
                case_id = acq.get("case_id")
                if case_id:
                    case = get_case(case_id) or {}
                    log_custody({
                        "id": uuid.uuid4().hex[:12],
                        "case_id": case_id,
                        "action": CustodyAction.EXTRACTION_STARTED.value,
                        "examiner": case.get("examiner", "system"),
                        "device_id": acq.get("device_id"),
                        "acquisition_id": self.acquisition_id,
                        "details": (
                            "iOS backup encryption enabled "
                            f"({'pre-existing' if already_on else 'set by Pixtra'})"
                        ),
                    })
            except Exception as e:
                logger.warning(f"Could not log custody event for passphrase: {e}")

            self._report(AcquisitionStatus.IN_PROGRESS, AcquisitionStage.RSYNC,
                         progress=5.0, message="Starting iTunes-style backup...")

            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pymobiledevice3", "backup2", "backup",
                "--udid", self.device_serial,
                "--full", backup_dir,
                stdout=None,
                stderr=None,
            )

            POLL_INTERVAL_SEC = 30
            HUNG_TIMEOUT_SEC = 600
            prev_files = 0
            prev_bytes = 0
            last_change_at = time.time()

            while True:
                if self._cancelled:
                    proc.kill()
                    await proc.wait()
                    return {"success": False, "error": "Cancelled by user",
                            "files_extracted": 0, "bytes_extracted": 0,
                            "output_path": backup_dir}

                try:
                    await asyncio.wait_for(proc.wait(), timeout=POLL_INTERVAL_SEC)
                    break
                except asyncio.TimeoutError:
                    pass

                cur_files = 0
                cur_bytes = 0
                for root, _dirs, files in os.walk(backup_dir):
                    for f in files:
                        cur_files += 1
                        try:
                            cur_bytes += os.path.getsize(os.path.join(root, f))
                        except OSError:
                            pass

                if cur_files == prev_files and cur_bytes == prev_bytes:
                    if time.time() - last_change_at > HUNG_TIMEOUT_SEC:
                        logger.error(
                            f"Backup hung: no progress for {HUNG_TIMEOUT_SEC}s "
                            f"({cur_files} files, {cur_bytes} bytes). Killing."
                        )
                        proc.kill()
                        await proc.wait()
                        return {
                            "success": False,
                            "error": "Backup appears hung - no progress for 10 minutes",
                            "files_extracted": cur_files,
                            "bytes_extracted": cur_bytes,
                            "output_path": backup_dir,
                        }
                else:
                    last_change_at = time.time()
                    prev_files = cur_files
                    prev_bytes = cur_bytes

                self.files_extracted = cur_files
                self.bytes_extracted = cur_bytes
                self._report(
                    AcquisitionStatus.IN_PROGRESS,
                    AcquisitionStage.RSYNC,
                    progress=50.0,
                    message=(
                        f"Backup in progress: {cur_files} files, "
                        f"{cur_bytes / (1024**2):.1f} MB"
                    ),
                )

            await proc.wait()

            if proc.returncode != 0:
                return {"success": False,
                        "error": (
                            f"pymobiledevice3 exited with code {proc.returncode} "
                            "(see backend logs / journalctl)"
                        ),
                        "files_extracted": self.files_extracted,
                        "bytes_extracted": self.bytes_extracted,
                        "output_path": backup_dir}

            udid_subdir = None
            try:
                for entry in os.listdir(backup_dir):
                    full = os.path.join(backup_dir, entry)
                    if os.path.isdir(full) and os.path.exists(
                        os.path.join(full, "Manifest.db")
                    ):
                        udid_subdir = full
                        break
            except OSError as e:
                logger.error(f"Could not list {backup_dir}: {e}")

            if not udid_subdir:
                return {
                    "success": False,
                    "error": (
                        f"Could not locate UDID subdirectory under {backup_dir} "
                        "after backup (no child directory contains Manifest.db)."
                    ),
                    "files_extracted": 0, "bytes_extracted": 0,
                    "output_path": backup_dir,
                }
            logger.info(f"Encrypted backup located at {udid_subdir}")

            self._report(AcquisitionStatus.IN_PROGRESS, AcquisitionStage.RSYNC,
                         progress=88.0, message="Decrypting backup...")

            try:
                from iphone_backup_decrypt import EncryptedBackup
            except ImportError as e:
                return {"success": False,
                        "error": f"iphone_backup_decrypt not installed: {e}",
                        "files_extracted": 0, "bytes_extracted": 0,
                        "output_path": backup_dir}

            def _do_decrypt():
                backup = EncryptedBackup(
                    backup_directory=udid_subdir, passphrase=passphrase
                )
                for domain in FORENSIC_DOMAINS:
                    try:
                        backup.extract_files(
                            domain_like=domain,
                            preserve_folders=True,
                            domain_subfolders=True,
                            output_folder=decrypted_dir,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Decrypt failed for domain {domain}: {e}"
                        )

            await asyncio.get_running_loop().run_in_executor(None, _do_decrypt)

            self._report(AcquisitionStatus.HASHING, AcquisitionStage.HASH,
                         progress=95.0, message="Hashing extracted files...")

            total_files = 0
            total_bytes = 0
            for root, _dirs, files in os.walk(decrypted_dir):
                for f in files:
                    fpath = os.path.join(root, f)
                    total_files += 1
                    try:
                        total_bytes += os.path.getsize(fpath)
                    except OSError:
                        pass

            self.files_extracted = total_files
            self.bytes_extracted = total_bytes

            self._report(AcquisitionStatus.COMPLETE, AcquisitionStage.COMPLETE,
                         progress=100.0,
                         message=f"Backup complete: {total_files} files, "
                                 f"{total_bytes / (1024**2):.1f} MB")

            return {
                "success": True,
                "files_extracted": total_files,
                "bytes_extracted": total_bytes,
                "output_path": decrypted_dir,
            }

        except asyncio.TimeoutError:
            return {"success": False, "error": "Backup timed out",
                    "files_extracted": 0, "bytes_extracted": 0,
                    "output_path": backup_dir}
        except Exception as e:
            logger.error(f"iOS logical extraction failed: {e}", exc_info=True)
            return {"success": False, "error": str(e),
                    "files_extracted": 0, "bytes_extracted": 0,
                    "output_path": backup_dir}


class Checkm8Extractor(BaseExtractor):

    async def extract(self) -> dict:
        self.start_time = time.time()
        extract_dir = os.path.join(self.output_dir, "checkm8_fs")
        os.makedirs(extract_dir, exist_ok=True)

        try:
            self._report(AcquisitionStatus.PREPARING, AcquisitionStage.DFU,
                         progress=0.0, message="Waiting for device in DFU mode...")

            if not await self._check_dfu():
                return {"success": False,
                        "error": "Device not in DFU mode. Follow on-screen instructions to enter DFU.",
                        "files_extracted": 0, "bytes_extracted": 0,
                        "output_path": extract_dir}

            self._report(AcquisitionStatus.IN_PROGRESS, AcquisitionStage.EXPLOIT,
                         progress=5.0, message="Running checkm8 exploit...")

            exploit_ok = await self._run_exploit()
            if not exploit_ok:
                return {"success": False, "error": "checkm8 exploit failed",
                        "files_extracted": 0, "bytes_extracted": 0,
                        "output_path": extract_dir}

            self._report(AcquisitionStatus.IN_PROGRESS, AcquisitionStage.SSH,
                         progress=15.0, message="Establishing SSH tunnel...")

            ssh_ok = await self._setup_ssh()
            if not ssh_ok:
                return {"success": False, "error": "SSH tunnel failed",
                        "files_extracted": 0, "bytes_extracted": 0,
                        "output_path": extract_dir}

            self._report(AcquisitionStatus.IN_PROGRESS, AcquisitionStage.RSYNC,
                         progress=20.0, message="Copying filesystem via rsync...")

            rsync_ok = await self._rsync_filesystem(extract_dir)
            if not rsync_ok:
                return {"success": False, "error": "Filesystem copy failed",
                        "files_extracted": self.files_extracted,
                        "bytes_extracted": self.bytes_extracted,
                        "output_path": extract_dir}

            self._report(AcquisitionStatus.IN_PROGRESS, AcquisitionStage.KEYCHAIN,
                         progress=85.0, message="Dumping keychain...")

            await self._dump_keychain(extract_dir)

            self._report(AcquisitionStatus.HASHING, AcquisitionStage.HASH,
                         progress=90.0, message="Generating hash manifest...")

            total_files = 0
            total_bytes = 0
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    total_files += 1
                    total_bytes += os.path.getsize(os.path.join(root, f))

            self.files_extracted = total_files
            self.bytes_extracted = total_bytes

            self._report(AcquisitionStatus.COMPLETE, AcquisitionStage.COMPLETE,
                         progress=100.0,
                         message=f"Extraction complete: {total_files} files, "
                                 f"{total_bytes / (1024**3):.1f} GB")

            return {
                "success": True,
                "files_extracted": total_files,
                "bytes_extracted": total_bytes,
                "output_path": extract_dir,
            }

        except Exception as e:
            logger.error(f"checkm8 extraction failed: {e}")
            return {"success": False, "error": str(e),
                    "files_extracted": self.files_extracted,
                    "bytes_extracted": self.bytes_extracted,
                    "output_path": extract_dir}

    async def _check_dfu(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "irecovery", "-q",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            return "DFU" in stdout.decode()
        except (FileNotFoundError, asyncio.TimeoutError):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "lsusb",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                output = stdout.decode()
                return "05ac:1227" in output
            except Exception:
                return False

    async def _run_exploit(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "palera1n", "-f",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            while True:
                if self._cancelled:
                    proc.kill()
                    return False
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=60)
                if not line:
                    break
                text = line.decode().strip()
                if text:
                    self._report(AcquisitionStatus.IN_PROGRESS, AcquisitionStage.EXPLOIT,
                                 progress=10.0, message=f"Exploit: {text}")
                    logger.info(f"[palera1n] {text}")

            await proc.wait()
            return proc.returncode == 0

        except Exception as e:
            logger.error(f"palera1n exploit failed: {e}")
            return False

    async def _setup_ssh(self) -> bool:
        try:
            self._iproxy = await asyncio.create_subprocess_exec(
                "iproxy", "2222", "44",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.sleep(2)

            proc = await asyncio.create_subprocess_exec(
                "ssh", "-p", "2222", "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=5",
                "root@localhost", "echo", "connected",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            return "connected" in stdout.decode()

        except Exception as e:
            logger.error(f"SSH setup failed: {e}")
            return False

    async def _rsync_filesystem(self, output_dir: str) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "rsync", "-avz", "--progress",
                "-e", "ssh -p 2222 -o StrictHostKeyChecking=no",
                "root@localhost:/",
                os.path.join(output_dir, "filesystem/"),
                "--exclude=/dev", "--exclude=/proc", "--exclude=/sys",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            while True:
                if self._cancelled:
                    proc.kill()
                    return False

                line = await asyncio.wait_for(proc.stdout.readline(), timeout=600)
                if not line:
                    break
                text = line.decode().strip()
                if text and not text.startswith("sending"):
                    self.files_extracted += 1
                    self._report(
                        AcquisitionStatus.IN_PROGRESS,
                        AcquisitionStage.RSYNC,
                        progress=20.0 + min(60.0, self.files_extracted / 100.0),
                        message=f"Copying: {self.files_extracted} files",
                        current_file=text[:80],
                    )

            await proc.wait()
            return proc.returncode == 0

        except Exception as e:
            logger.error(f"rsync failed: {e}")
            return False

    async def _dump_keychain(self, output_dir: str) -> bool:
        keychain_dir = os.path.join(output_dir, "keychain")
        os.makedirs(keychain_dir, exist_ok=True)
        try:
            proc = await asyncio.create_subprocess_exec(
                "ssh", "-p", "2222", "-o", "StrictHostKeyChecking=no",
                "root@localhost",
                "keychain-dumper", "-a",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            keychain_path = os.path.join(keychain_dir, "keychain_dump.xml")
            with open(keychain_path, "wb") as f:
                f.write(stdout)
            return True
        except Exception as e:
            logger.warning(f"Keychain dump failed (non-fatal): {e}")
            return False


class ADBLogicalExtractor(BaseExtractor):

    PULL_DIRS = [
        "/sdcard/DCIM",
        "/sdcard/Pictures",
        "/sdcard/Download",
        "/sdcard/Documents",
        "/sdcard/WhatsApp",
        "/sdcard/Telegram",
        "/sdcard/Movies",
        "/sdcard/Music",
        "/sdcard/Recordings",
        "/sdcard/Voice Recorder",
    ]

    async def extract(self) -> dict:
        self.start_time = time.time()
        extract_dir = os.path.join(self.output_dir, "adb_logical")
        os.makedirs(extract_dir, exist_ok=True)

        try:
            self._report(AcquisitionStatus.PREPARING, AcquisitionStage.DETECT,
                         progress=0.0, message="Connecting to Android device...")

            info_path = os.path.join(extract_dir, "device_info.json")
            await self._dump_device_info(info_path)

            self._report(AcquisitionStatus.IN_PROGRESS, AcquisitionStage.RSYNC,
                         progress=5.0, message="Pulling data from device...")

            total_dirs = len(self.PULL_DIRS)
            for i, remote_dir in enumerate(self.PULL_DIRS):
                if self._cancelled:
                    return {"success": False, "error": "Cancelled",
                            "files_extracted": self.files_extracted,
                            "bytes_extracted": self.bytes_extracted,
                            "output_path": extract_dir}

                dir_name = remote_dir.split("/")[-1]
                local_dir = os.path.join(extract_dir, dir_name)
                pct = 5.0 + (80.0 * i / total_dirs)
                self._report(AcquisitionStatus.IN_PROGRESS, AcquisitionStage.RSYNC,
                             progress=pct, message=f"Pulling {dir_name}...")

                await self._adb_pull(remote_dir, local_dir)

            self._report(AcquisitionStatus.IN_PROGRESS, AcquisitionStage.RSYNC,
                         progress=85.0, message="Listing installed apps...")
            await self._dump_app_list(os.path.join(extract_dir, "app_list.json"))

            self._report(AcquisitionStatus.IN_PROGRESS, AcquisitionStage.RSYNC,
                         progress=88.0, message="Extracting contacts and call log...")
            await self._dump_contacts(os.path.join(extract_dir, "contacts.json"))
            await self._dump_call_log(os.path.join(extract_dir, "call_log.json"))
            await self._dump_sms(os.path.join(extract_dir, "sms.txt"))
            await self._dump_wifi_networks(os.path.join(extract_dir, "wifi_networks.txt"))

            total_files = 0
            total_bytes = 0
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    total_files += 1
                    total_bytes += os.path.getsize(os.path.join(root, f))

            self.files_extracted = total_files
            self.bytes_extracted = total_bytes

            self._report(AcquisitionStatus.COMPLETE, AcquisitionStage.COMPLETE,
                         progress=100.0,
                         message=f"Extraction complete: {total_files} files, "
                                 f"{total_bytes / (1024**2):.1f} MB")

            return {
                "success": True,
                "files_extracted": total_files,
                "bytes_extracted": total_bytes,
                "output_path": extract_dir,
            }

        except Exception as e:
            logger.error(f"ADB logical extraction failed: {e}")
            return {"success": False, "error": str(e),
                    "files_extracted": self.files_extracted,
                    "bytes_extracted": self.bytes_extracted,
                    "output_path": extract_dir}

    async def _adb_pull(self, remote: str, local: str):
        os.makedirs(local, exist_ok=True)
        try:
            proc = await asyncio.create_subprocess_exec(
                "adb", "-s", self.device_serial, "pull", remote, local,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            for line in stdout.decode().split("\n"):
                if "pulled" in line.lower():
                    logger.info(f"[adb] {line.strip()}")
        except asyncio.TimeoutError:
            logger.warning(f"adb pull timed out for {remote}")
        except Exception as e:
            logger.warning(f"adb pull failed for {remote}: {e}")

    async def _dump_device_info(self, output_path: str):
        try:
            proc = await asyncio.create_subprocess_exec(
                "adb", "-s", self.device_serial, "shell", "getprop",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            props = {}
            for line in stdout.decode().split("\n"):
                if ": [" in line:
                    key = line.split("[")[1].split("]")[0] if "[" in line else ""
                    val = line.split("[")[2].split("]")[0] if line.count("[") > 1 else ""
                    if key:
                        props[key] = val
            with open(output_path, "w") as f:
                json.dump(props, f, indent=2)
        except Exception as e:
            logger.warning(f"Device info dump failed: {e}")

    async def _dump_app_list(self, output_path: str):
        try:
            proc = await asyncio.create_subprocess_exec(
                "adb", "-s", self.device_serial, "shell",
                "pm", "list", "packages", "-f",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            apps = []
            for line in stdout.decode().split("\n"):
                line = line.strip()
                if line.startswith("package:"):
                    parts = line[8:].rsplit("=", 1)
                    if len(parts) == 2:
                        apps.append({"apk_path": parts[0], "package": parts[1]})
            with open(output_path, "w") as f:
                json.dump(apps, f, indent=2)
        except Exception as e:
            logger.warning(f"App list dump failed: {e}")

    async def _dump_contacts(self, output_path: str):
        try:
            proc = await asyncio.create_subprocess_exec(
                "adb", "-s", self.device_serial, "shell",
                "content", "query", "--uri", "content://contacts/phones",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = stdout.decode()
            if output.strip() and "Error" not in output and "Permission" not in output:
                with open(output_path, "w") as f:
                    f.write(output)
                return
        except Exception as e:
            logger.warning(f"Content provider contacts failed: {e}")

        try:
            proc = await asyncio.create_subprocess_exec(
                "adb", "-s", self.device_serial, "shell",
                "dumpsys", "contacts",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            output = stdout.decode()
            if output.strip():
                with open(output_path.replace(".json", "_dumpsys.txt"), "w") as f:
                    f.write(output)
        except Exception as e:
            logger.warning(f"Dumpsys contacts also failed: {e}")

    async def _dump_call_log(self, output_path: str):
        try:
            proc = await asyncio.create_subprocess_exec(
                "adb", "-s", self.device_serial, "shell",
                "content", "query", "--uri", "content://call_log/calls",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = stdout.decode()
            if output.strip() and "Error" not in output and "Permission" not in output:
                with open(output_path, "w") as f:
                    f.write(output)
                return
        except Exception as e:
            logger.warning(f"Content provider call log failed: {e}")

        try:
            proc = await asyncio.create_subprocess_exec(
                "adb", "-s", self.device_serial, "shell",
                "dumpsys", "telecom",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            output = stdout.decode()
            if output.strip():
                with open(output_path.replace(".json", "_dumpsys.txt"), "w") as f:
                    f.write(output)
        except Exception as e:
            logger.warning(f"Dumpsys telecom also failed: {e}")

    async def _dump_sms(self, output_path: str):
        try:
            proc = await asyncio.create_subprocess_exec(
                "adb", "-s", self.device_serial, "shell",
                "content", "query", "--uri", "content://sms",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            output = stdout.decode()
            if output.strip() and "Error" not in output:
                with open(output_path, "w") as f:
                    f.write(output)
        except Exception as e:
            logger.warning(f"SMS extraction failed: {e}")

    async def _dump_wifi_networks(self, output_path: str):
        try:
            proc = await asyncio.create_subprocess_exec(
                "adb", "-s", self.device_serial, "shell",
                "dumpsys", "wifi",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            with open(output_path, "w") as f:
                f.write(stdout.decode())
        except Exception as e:
            logger.warning(f"WiFi dump failed: {e}")


class MTKBypassExtractor(BaseExtractor):

    async def extract(self) -> dict:
        self.start_time = time.time()
        extract_dir = os.path.join(self.output_dir, "mtk_dump")
        os.makedirs(extract_dir, exist_ok=True)

        try:
            self._report(AcquisitionStatus.PREPARING, AcquisitionStage.DETECT,
                         progress=0.0,
                         message="Connecting to MediaTek device in BROM/preloader mode...")

            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "mtkclient", "rl",
                extract_dir, "--skip", "userdata",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            while True:
                if self._cancelled:
                    proc.kill()
                    return {"success": False, "error": "Cancelled",
                            "files_extracted": 0, "bytes_extracted": 0,
                            "output_path": extract_dir}

                line = await asyncio.wait_for(proc.stderr.readline(), timeout=600)
                if not line:
                    break
                text = line.decode().strip()
                if text:
                    if "%" in text:
                        try:
                            pct = float(text.split("%")[0].split()[-1])
                            self._report(AcquisitionStatus.IN_PROGRESS,
                                         AcquisitionStage.RSYNC,
                                         progress=pct * 0.9,
                                         message=text[:80])
                        except (ValueError, IndexError):
                            pass
                    logger.info(f"[mtkclient] {text}")

            await proc.wait()

            if proc.returncode != 0:
                stderr = (await proc.stderr.read()).decode()
                return {"success": False, "error": f"mtkclient failed: {stderr[:200]}",
                        "files_extracted": 0, "bytes_extracted": 0,
                        "output_path": extract_dir}

            total_files = 0
            total_bytes = 0
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    total_files += 1
                    total_bytes += os.path.getsize(os.path.join(root, f))

            self.files_extracted = total_files
            self.bytes_extracted = total_bytes

            self._report(AcquisitionStatus.COMPLETE, AcquisitionStage.COMPLETE,
                         progress=100.0,
                         message=f"MTK dump complete: {total_files} partitions, "
                                 f"{total_bytes / (1024**3):.1f} GB")

            return {
                "success": True,
                "files_extracted": total_files,
                "bytes_extracted": total_bytes,
                "output_path": extract_dir,
            }

        except Exception as e:
            logger.error(f"MTK extraction failed: {e}")
            return {"success": False, "error": str(e),
                    "files_extracted": 0, "bytes_extracted": 0,
                    "output_path": extract_dir}


class EDLExtractor(BaseExtractor):

    async def extract(self) -> dict:
        self.start_time = time.time()
        extract_dir = os.path.join(self.output_dir, "edl_dump")
        os.makedirs(extract_dir, exist_ok=True)

        try:
            self._report(AcquisitionStatus.PREPARING, AcquisitionStage.DETECT,
                         progress=0.0, message="Connecting to device in EDL mode...")

            proc = await asyncio.create_subprocess_exec(
                "edl", "rl", extract_dir, "--memory=ufs",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            while True:
                if self._cancelled:
                    proc.kill()
                    return {"success": False, "error": "Cancelled",
                            "files_extracted": 0, "bytes_extracted": 0,
                            "output_path": extract_dir}

                line = await asyncio.wait_for(proc.stdout.readline(), timeout=600)
                if not line:
                    break
                text = line.decode().strip()
                if text:
                    logger.info(f"[edl] {text}")
                    self._report(AcquisitionStatus.IN_PROGRESS, AcquisitionStage.RSYNC,
                                 message=text[:80])

            await proc.wait()

            total_files = 0
            total_bytes = 0
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    total_files += 1
                    total_bytes += os.path.getsize(os.path.join(root, f))

            self.files_extracted = total_files
            self.bytes_extracted = total_bytes

            self._report(AcquisitionStatus.COMPLETE, AcquisitionStage.COMPLETE,
                         progress=100.0,
                         message=f"EDL dump complete: {total_files} partitions")

            return {
                "success": True,
                "files_extracted": total_files,
                "bytes_extracted": total_bytes,
                "output_path": extract_dir,
            }

        except Exception as e:
            logger.error(f"EDL extraction failed: {e}")
            return {"success": False, "error": str(e),
                    "files_extracted": 0, "bytes_extracted": 0,
                    "output_path": extract_dir}


EXTRACTOR_MAP = {
    ExtractionMethod.LOGICAL_BACKUP: IOSLogicalExtractor,
    ExtractionMethod.ADVANCED_LOGICAL: IOSLogicalExtractor,
    ExtractionMethod.CHECKM8_FILESYSTEM: Checkm8Extractor,
    ExtractionMethod.CHECKM8_PHYSICAL: Checkm8Extractor,
    ExtractionMethod.ADB_LOGICAL: ADBLogicalExtractor,
    ExtractionMethod.ADB_BACKUP: ADBLogicalExtractor,
    ExtractionMethod.MTK_BYPASS: MTKBypassExtractor,
    ExtractionMethod.EDL_EXTRACTION: EDLExtractor,
}


def get_extractor(
    method: ExtractionMethod,
    acquisition_id: str,
    device_serial: str,
    output_dir: str,
    progress_cb: Optional[ProgressCallback] = None,
) -> BaseExtractor:
    cls = EXTRACTOR_MAP.get(method)
    if cls is None:
        raise ValueError(f"Unsupported extraction method: {method}")
    return cls(
        acquisition_id=acquisition_id,
        device_serial=device_serial,
        output_dir=output_dir,
        progress_cb=progress_cb,
    )

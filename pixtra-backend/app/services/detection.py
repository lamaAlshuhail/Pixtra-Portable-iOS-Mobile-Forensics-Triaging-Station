import asyncio
import inspect
import os
import subprocess
import logging
from typing import Optional

from app.models.schemas import (
    DetectedDevice,
    DevicePlatform,
    ExtractionCapability,
    ExtractionMethod,
)

logger = logging.getLogger("pixtra.detect")

import shutil as _shutil
ADB_PATH = os.environ.get("PIXTRA_ADB_PATH") or _shutil.which("adb") or "/usr/bin/adb"

IOS_CHIP_MAP = {
    "S8000": ("A9", "checkm8"),
    "S8003": ("A9", "checkm8"),
    "T8010": ("A10 Fusion", "checkm8"),
    "T8011": ("A10X Fusion", "checkm8"),
    "T8015": ("A11 Bionic", "checkm8"),
    "T8020": ("A12 Bionic", "agent"),
    "T8027": ("A12X Bionic", "agent"),
    "T8030": ("A13 Bionic", "agent"),
    "T8101": ("A14 Bionic", "agent"),
    "T8103": ("M1", "agent"),
    "T8110": ("A15 Bionic", "agent"),
    "T8112": ("M2", "logical_only"),
    "T8120": ("A16 Bionic", "logical_only"),
    "T8130": ("A17 Pro", "logical_only"),
    "T8140": ("A18", "logical_only"),
    "T8150": ("A19", "logical_only"),
}

CHECKM8_CHIPS = {"A7", "A8", "A8X", "A9", "A9X", "A10 Fusion", "A10X Fusion", "A11 Bionic"}


def _ensure_usbmuxd() -> None:
    try:
        subprocess.run(
            ["sudo", "systemctl", "start", "usbmuxd"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


async def _maybe_await(result):
    if inspect.isawaitable(result):
        return await result
    return result


async def _detect_ios_async() -> list[DetectedDevice]:
    from pymobiledevice3.usbmux import list_devices as list_usbmux_devices
    from pymobiledevice3.lockdown import create_using_usbmux

    connected = await _maybe_await(list_usbmux_devices())
    logger.info(f"pymobiledevice3 found {len(connected)} USB device(s)")

    devices: list[DetectedDevice] = []
    for mux_device in connected:
        try:
            udid = getattr(mux_device, "serial", None) or str(mux_device)
            logger.info(f"Querying lockdown for UDID={udid}")

            lockdown = await _maybe_await(create_using_usbmux(serial=udid))
            vals = lockdown.all_values

            serial = vals.get("SerialNumber", udid)
            product_type = vals.get("ProductType", "")
            product_version = vals.get("ProductVersion", "")
            device_name = vals.get("DeviceName", "")
            hw_platform = (vals.get("HardwarePlatform") or "").upper()

            from app.services.device_profiles import lookup_profile
            profile = lookup_profile(product_type)

            if profile:
                chipset = profile.chipset
                model_name = profile.model_name
                capabilities = list(profile.capabilities)
                recommended = profile.recommended_method
            else:
                chip_info = IOS_CHIP_MAP.get(hw_platform, ("Unknown", "logical_only"))
                chipset = chip_info[0]
                model_name = (
                    vals.get("MarketingName")
                    or device_name
                    or product_type
                    or "Unknown iPhone"
                )
                capabilities = [ExtractionCapability.LOGICAL]
                recommended = ExtractionMethod.LOGICAL_BACKUP

            detected = DetectedDevice(
                serial=serial,
                udid=udid,
                platform=DevicePlatform.IOS,
                model=product_type,
                model_name=model_name,
                chipset=chipset,
                os_version=product_version,
                capabilities=capabilities,
                recommended_method=recommended,
            )
            devices.append(detected)
            logger.info(
                f"Detected iOS: {model_name} ({product_type})"
                f" iOS {product_version} chip={chipset} UDID={udid}"
            )
        except Exception as e:
            logger.warning(f"Could not query device {mux_device}: {e}")

    return devices


async def detect_ios_devices() -> list[DetectedDevice]:
    _ensure_usbmuxd()

    try:
        return await _detect_ios_async()
    except ImportError:
        logger.info("pymobiledevice3 not installed - skipping iOS detection")
        return []
    except Exception as e:
        logger.error(f"iOS detection error: {e}", exc_info=True)
        return []


def detect_android_devices() -> list[DetectedDevice]:
    devices = []

    try:
        result = subprocess.run(
            [ADB_PATH, "devices", "-l"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            logger.warning(f"adb devices failed: {result.stderr}")
            return devices

        for line in result.stdout.strip().split("\n")[1:]:
            if not line.strip() or "offline" in line:
                continue

            parts = line.split()
            if len(parts) < 2:
                continue

            serial = parts[0]
            status = parts[1]

            if status != "device":
                devices.append(DetectedDevice(
                    serial=serial,
                    platform=DevicePlatform.ANDROID,
                    model_name=f"Android ({status})",
                    usb_debug_enabled=status == "device",
                    capabilities=[],
                    recommended_method=None,
                ))
                continue

            info = _get_android_device_info(serial)
            chipset = info.get("chipset", "Unknown")

            capabilities = [ExtractionCapability.LOGICAL]
            recommended = ExtractionMethod.ADB_LOGICAL

            if "mt6" in chipset.lower() or "mt8" in chipset.lower():
                capabilities.append(ExtractionCapability.MTK_BYPASS)
                recommended = ExtractionMethod.MTK_BYPASS

            if any(q in chipset.lower() for q in ["msm89", "msm8953", "sdm6"]):
                capabilities.append(ExtractionCapability.EDL)
                recommended = ExtractionMethod.EDL_EXTRACTION

            if info.get("is_rooted"):
                capabilities.append(ExtractionCapability.FILESYSTEM)
                recommended = ExtractionMethod.ADB_ROOT

            detected = DetectedDevice(
                serial=serial,
                platform=DevicePlatform.ANDROID,
                model=info.get("model"),
                model_name=info.get("model_name"),
                chipset=chipset,
                os_version=info.get("os_version"),
                storage_gb=info.get("storage_gb"),
                battery_percent=info.get("battery_percent"),
                usb_debug_enabled=True,
                capabilities=capabilities,
                recommended_method=recommended,
            )
            devices.append(detected)

    except FileNotFoundError:
        logger.info(f"adb not found at {ADB_PATH} - skipping Android detection")
    except subprocess.TimeoutExpired:
        logger.warning("adb timed out during device detection")
    except Exception as e:
        logger.error(f"Android detection error: {e}")

    return devices


def _get_android_device_info(serial: str) -> dict:
    info = {}

    def getprop(prop: str) -> str:
        try:
            r = subprocess.run(
                [ADB_PATH, "-s", serial, "shell", "getprop", prop],
                capture_output=True, text=True, timeout=5,
            )
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            return ""

    info["model"] = getprop("ro.product.model")
    info["model_name"] = getprop("ro.product.marketname") or getprop("ro.product.model")
    info["os_version"] = getprop("ro.build.version.release")
    info["chipset"] = (
        getprop("ro.hardware.chipname")
        or getprop("ro.board.platform")
        or getprop("ro.hardware")
    )

    try:
        r = subprocess.run(
            [ADB_PATH, "-s", serial, "shell", "dumpsys", "battery"],
            capture_output=True, text=True, timeout=5,
        )
        for line in r.stdout.split("\n"):
            if "level:" in line:
                info["battery_percent"] = int(line.split(":")[-1].strip())
                break
    except Exception:
        pass

    try:
        r = subprocess.run(
            [ADB_PATH, "-s", serial, "shell", "su", "-c", "id"],
            capture_output=True, text=True, timeout=3,
        )
        info["is_rooted"] = "uid=0" in r.stdout
    except Exception:
        info["is_rooted"] = False

    return info


async def detect_all_devices() -> list[DetectedDevice]:
    ios = await detect_ios_devices()
    android = detect_android_devices()
    return ios + android

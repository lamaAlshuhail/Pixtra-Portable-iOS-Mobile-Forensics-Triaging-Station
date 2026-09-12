import json
import logging
import os
from typing import Optional

from app.models.schemas import (
    DeviceProfile,
    DevicePlatform,
    ExtractionCapability,
    ExtractionMethod,
)

logger = logging.getLogger("pixtra.profiles")

_profiles: dict[str, DeviceProfile] = {}

PROFILES_DIR = os.environ.get("PIXTRA_PROFILES_DIR", "data/device_profiles")


def load_device_profiles():
    _profiles.clear()

    if os.path.isdir(PROFILES_DIR):
        for fname in os.listdir(PROFILES_DIR):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(PROFILES_DIR, fname)) as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            profile = DeviceProfile(**item)
                            _profiles[profile.model_id] = profile
                    elif isinstance(data, dict):
                        profile = DeviceProfile(**data)
                        _profiles[profile.model_id] = profile
                except Exception as e:
                    logger.warning(f"Failed to load profile {fname}: {e}")

    _load_builtin_ios()
    _load_builtin_android()

    logger.info(f"Loaded {len(_profiles)} device profiles")


def _load_builtin_ios():
    ios_devices = [
        ("iPhone6,1", "iPhone 5s", "A7", "S5L8960", ["logical", "filesystem", "physical", "checkm8"], "checkm8_filesystem"),
        ("iPhone6,2", "iPhone 5s", "A7", "S5L8960", ["logical", "filesystem", "physical", "checkm8"], "checkm8_filesystem"),
        ("iPhone7,1", "iPhone 6 Plus", "A8", "T7000", ["logical", "filesystem", "physical", "checkm8"], "checkm8_filesystem"),
        ("iPhone7,2", "iPhone 6", "A8", "T7000", ["logical", "filesystem", "physical", "checkm8"], "checkm8_filesystem"),
        ("iPhone8,1", "iPhone 6s", "A9", "S8000", ["logical", "filesystem", "physical", "checkm8"], "checkm8_filesystem"),
        ("iPhone8,2", "iPhone 6s Plus", "A9", "S8000", ["logical", "filesystem", "physical", "checkm8"], "checkm8_filesystem"),
        ("iPhone8,4", "iPhone SE (1st gen)", "A9", "S8003", ["logical", "filesystem", "physical", "checkm8"], "checkm8_filesystem"),
        ("iPhone9,1", "iPhone 7", "A10 Fusion", "T8010", ["logical", "filesystem", "physical", "checkm8"], "checkm8_filesystem"),
        ("iPhone9,2", "iPhone 7 Plus", "A10 Fusion", "T8010", ["logical", "filesystem", "physical", "checkm8"], "checkm8_filesystem"),
        ("iPhone9,3", "iPhone 7", "A10 Fusion", "T8010", ["logical", "filesystem", "physical", "checkm8"], "checkm8_filesystem"),
        ("iPhone9,4", "iPhone 7 Plus", "A10 Fusion", "T8010", ["logical", "filesystem", "physical", "checkm8"], "checkm8_filesystem"),
        ("iPhone10,1", "iPhone 8", "A11 Bionic", "T8015", ["logical", "filesystem", "physical", "checkm8"], "checkm8_filesystem"),
        ("iPhone10,2", "iPhone 8 Plus", "A11 Bionic", "T8015", ["logical", "filesystem", "physical", "checkm8"], "checkm8_filesystem"),
        ("iPhone10,3", "iPhone X", "A11 Bionic", "T8015", ["logical", "filesystem", "physical", "checkm8"], "checkm8_filesystem"),
        ("iPhone10,4", "iPhone 8", "A11 Bionic", "T8015", ["logical", "filesystem", "physical", "checkm8"], "checkm8_filesystem"),
        ("iPhone10,5", "iPhone 8 Plus", "A11 Bionic", "T8015", ["logical", "filesystem", "physical", "checkm8"], "checkm8_filesystem"),
        ("iPhone10,6", "iPhone X", "A11 Bionic", "T8015", ["logical", "filesystem", "physical", "checkm8"], "checkm8_filesystem"),
        ("iPhone11,2", "iPhone XS", "A12 Bionic", "T8020", ["logical", "filesystem"], "agent_based"),
        ("iPhone11,4", "iPhone XS Max", "A12 Bionic", "T8020", ["logical", "filesystem"], "agent_based"),
        ("iPhone11,6", "iPhone XS Max", "A12 Bionic", "T8020", ["logical", "filesystem"], "agent_based"),
        ("iPhone11,8", "iPhone XR", "A12 Bionic", "T8020", ["logical", "filesystem"], "agent_based"),
        ("iPhone12,1", "iPhone 11", "A13 Bionic", "T8030", ["logical", "filesystem"], "agent_based"),
        ("iPhone12,3", "iPhone 11 Pro", "A13 Bionic", "T8030", ["logical", "filesystem"], "agent_based"),
        ("iPhone12,5", "iPhone 11 Pro Max", "A13 Bionic", "T8030", ["logical", "filesystem"], "agent_based"),
        ("iPhone13,1", "iPhone 12 mini", "A14 Bionic", "T8101", ["logical", "filesystem"], "agent_based"),
        ("iPhone13,2", "iPhone 12", "A14 Bionic", "T8101", ["logical", "filesystem"], "agent_based"),
        ("iPhone13,3", "iPhone 12 Pro", "A14 Bionic", "T8101", ["logical", "filesystem"], "agent_based"),
        ("iPhone13,4", "iPhone 12 Pro Max", "A14 Bionic", "T8101", ["logical", "filesystem"], "agent_based"),
        ("iPhone14,2", "iPhone 13 Pro", "A15 Bionic", "T8110", ["logical", "filesystem"], "agent_based"),
        ("iPhone14,3", "iPhone 13 Pro Max", "A15 Bionic", "T8110", ["logical", "filesystem"], "agent_based"),
        ("iPhone14,4", "iPhone 13 mini", "A15 Bionic", "T8110", ["logical", "filesystem"], "agent_based"),
        ("iPhone14,5", "iPhone 13", "A15 Bionic", "T8110", ["logical", "filesystem"], "agent_based"),
        ("iPhone14,6", "iPhone SE (3rd gen)", "A15 Bionic", "T8110", ["logical", "filesystem"], "agent_based"),
        ("iPhone14,7", "iPhone 14", "A15 Bionic", "T8110", ["logical"], "logical_backup"),
        ("iPhone14,8", "iPhone 14 Plus", "A15 Bionic", "T8110", ["logical"], "logical_backup"),
        ("iPhone15,2", "iPhone 14 Pro", "A16 Bionic", "T8120", ["logical"], "logical_backup"),
        ("iPhone15,3", "iPhone 14 Pro Max", "A16 Bionic", "T8120", ["logical"], "logical_backup"),
        ("iPhone15,4", "iPhone 15", "A16 Bionic", "T8120", ["logical"], "logical_backup"),
        ("iPhone15,5", "iPhone 15 Plus", "A16 Bionic", "T8120", ["logical"], "logical_backup"),
        ("iPhone16,1", "iPhone 15 Pro", "A17 Pro", "T8130", ["logical"], "logical_backup"),
        ("iPhone16,2", "iPhone 15 Pro Max", "A17 Pro", "T8130", ["logical"], "logical_backup"),
        ("iPhone17,1", "iPhone 16 Pro", "A18 Pro", "T8140", ["logical"], "logical_backup"),
        ("iPhone17,2", "iPhone 16 Pro Max", "A18 Pro", "T8140", ["logical"], "logical_backup"),
        ("iPhone17,3", "iPhone 16", "A18", "T8140", ["logical"], "logical_backup"),
        ("iPhone17,4", "iPhone 16 Plus", "A18", "T8140", ["logical"], "logical_backup"),
        ("iPhone17,5", "iPhone SE (4th gen)", "A18", "T8140", ["logical"], "logical_backup"),
        ("iPhone18,1", "iPhone 17 Pro", "A19 Pro", "T8150", ["logical"], "logical_backup"),
        ("iPhone18,2", "iPhone 17 Pro Max", "A19 Pro", "T8150", ["logical"], "logical_backup"),
        ("iPhone18,3", "iPhone 17", "A19", "T8150", ["logical"], "logical_backup"),
        ("iPhone18,4", "iPhone 17 Air", "A19", "T8150", ["logical"], "logical_backup"),
        ("iPhone18,5", "iPhone 17 Plus", "A19", "T8150", ["logical"], "logical_backup"),
    ]

    for model_id, name, chipset, chip_code, caps, method in ios_devices:
        if model_id not in _profiles:
            _profiles[model_id] = DeviceProfile(
                model_id=model_id,
                model_name=name,
                vendor="Apple",
                platform=DevicePlatform.IOS,
                chipset=chipset,
                chip_code=chip_code,
                capabilities=[ExtractionCapability(c) for c in caps],
                recommended_method=ExtractionMethod(method),
            )


def _load_builtin_android():
    android_devices = [
        ("Redmi Note 8", "Xiaomi", "MT6785 Helio G90T", "mt6785", ["logical", "mtk_bypass"], "mtk_bypass"),
        ("Redmi Note 9", "Xiaomi", "MT6769 Helio G85", "mt6769", ["logical", "mtk_bypass"], "mtk_bypass"),
        ("Redmi Note 10", "Xiaomi", "MT6769 Helio G85", "mt6769", ["logical", "mtk_bypass"], "mtk_bypass"),
        ("Redmi 9", "Xiaomi", "MT6769 Helio G80", "mt6769", ["logical", "mtk_bypass"], "mtk_bypass"),
        ("POCO M3", "Xiaomi", "MT6769 Helio G35", "mt6769", ["logical", "mtk_bypass"], "mtk_bypass"),
        ("Realme C3", "Realme", "MT6765 Helio G70", "mt6765", ["logical", "mtk_bypass"], "mtk_bypass"),
        ("Realme 6", "Realme", "MT6785 Helio G90T", "mt6785", ["logical", "mtk_bypass"], "mtk_bypass"),
        ("Oppo A5s", "Oppo", "MT6765 Helio P35", "mt6765", ["logical", "mtk_bypass"], "mtk_bypass"),
        ("Oppo A15", "Oppo", "MT6765 Helio P35", "mt6765", ["logical", "mtk_bypass"], "mtk_bypass"),
        ("Vivo Y20", "Vivo", "MT6765 Helio P35", "mt6765", ["logical", "mtk_bypass"], "mtk_bypass"),
        ("Samsung A10", "Samsung", "Exynos 7884", None, ["logical"], "adb_logical"),
        ("Samsung A21s", "Samsung", "Exynos 850", None, ["logical"], "adb_logical"),
        ("Samsung J7", "Samsung", "MSM8953", "msm8953", ["logical", "edl"], "edl_extraction"),
        ("Moto G5", "Motorola", "MSM8937", "msm8937", ["logical", "edl"], "edl_extraction"),
        ("LG G6", "LG", "MSM8996", "msm8996", ["logical", "edl"], "edl_extraction"),
        ("Nokia 6", "Nokia", "MSM8937", "msm8937", ["logical", "edl"], "edl_extraction"),
        ("Galaxy S24", "Samsung", "Snapdragon 8 Gen 3", "sm8650", ["logical"], "adb_logical"),
        ("Galaxy S23", "Samsung", "Snapdragon 8 Gen 2", "sm8550", ["logical"], "adb_logical"),
        ("Pixel 8", "Google", "Tensor G3", "zuma", ["logical"], "adb_logical"),
        ("Pixel 7", "Google", "Tensor G2", "cloudripper", ["logical"], "adb_logical"),
    ]

    for name, vendor, chipset, chip_code, caps, method in android_devices:
        model_id = name.replace(" ", "_").lower()
        if model_id not in _profiles:
            _profiles[model_id] = DeviceProfile(
                model_id=model_id,
                model_name=name,
                vendor=vendor,
                platform=DevicePlatform.ANDROID,
                chipset=chipset,
                chip_code=chip_code,
                capabilities=[ExtractionCapability(c) for c in caps],
                recommended_method=ExtractionMethod(method),
            )


def lookup_profile(model_id: str) -> Optional[DeviceProfile]:
    return _profiles.get(model_id)


def search_profiles(query: str, platform: Optional[str] = None) -> list[DeviceProfile]:
    query_lower = query.lower()
    results = []
    for p in _profiles.values():
        if platform and p.platform.value != platform:
            continue
        searchable = f"{p.model_id} {p.model_name} {p.vendor} {p.chipset}".lower()
        if query_lower in searchable:
            results.append(p)
    return results


def list_all_profiles(platform: Optional[str] = None) -> list[DeviceProfile]:
    if platform:
        return [p for p in _profiles.values() if p.platform.value == platform]
    return list(_profiles.values())


def get_profile_count() -> int:
    return len(_profiles)

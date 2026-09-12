import hashlib
import os
from pathlib import Path
from datetime import datetime
from typing import Optional


def hash_file(file_path: str, algorithms: list[str] = None) -> dict:
    if algorithms is None:
        algorithms = ["sha256", "md5", "sha1"]

    hashers = {alg: hashlib.new(alg) for alg in algorithms}
    size = 0

    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            size += len(chunk)
            for h in hashers.values():
                h.update(chunk)

    result = {
        "file_path": file_path,
        "size_bytes": size,
        "hashed_at": datetime.utcnow().isoformat(),
    }
    for alg, h in hashers.items():
        result[alg] = h.hexdigest()

    return result


def hash_directory(
    dir_path: str,
    algorithms: list[str] = None,
    progress_callback=None,
) -> list[dict]:
    if algorithms is None:
        algorithms = ["sha256", "md5", "sha1"]

    all_files = []
    for root, dirs, files in os.walk(dir_path):
        for fname in sorted(files):
            all_files.append(os.path.join(root, fname))

    total = len(all_files)
    results = []

    for i, fpath in enumerate(all_files):
        try:
            h = hash_file(fpath, algorithms)
            h["file_path"] = os.path.relpath(fpath, dir_path)
            results.append(h)
        except (PermissionError, OSError) as e:
            results.append({
                "file_path": os.path.relpath(fpath, dir_path),
                "error": str(e),
                "size_bytes": 0,
                "hashed_at": datetime.utcnow().isoformat(),
            })

        if progress_callback:
            progress_callback(fpath, i + 1, total)

    return results


def verify_file(file_path: str, expected_sha256: str) -> dict:
    try:
        actual = hash_file(file_path, ["sha256"])
        return {
            "file_path": file_path,
            "expected_sha256": expected_sha256,
            "actual_sha256": actual["sha256"],
            "match": actual["sha256"] == expected_sha256,
            "verified_at": datetime.utcnow().isoformat(),
        }
    except (FileNotFoundError, OSError) as e:
        return {
            "file_path": file_path,
            "expected_sha256": expected_sha256,
            "actual_sha256": None,
            "match": False,
            "error": str(e),
            "verified_at": datetime.utcnow().isoformat(),
        }


def verify_manifest(manifest: list[dict], base_path: str) -> list[dict]:
    results = []
    for entry in manifest:
        fpath = os.path.join(base_path, entry["file_path"])
        result = verify_file(fpath, entry["sha256"])
        results.append(result)
    return results

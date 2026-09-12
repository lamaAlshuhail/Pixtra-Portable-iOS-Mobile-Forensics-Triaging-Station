import hashlib
import json
from pathlib import Path
from typing import Iterable


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def build_manifest(files: Iterable[Path], root: Path) -> dict:
    manifest: dict[str, str] = {}
    for p in files:
        if p.is_file():
            manifest[str(p.relative_to(root)).replace("\\", "/")] = sha256_file(p)
    return manifest


def write_manifest(manifest: dict, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8")
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def verify_manifest(manifest_path: Path, root: Path) -> dict:
    stored = json.loads(manifest_path.read_text(encoding="utf-8"))
    matched: list[str] = []
    mismatched: list[str] = []
    missing: list[str] = []

    for rel, expected in stored.items():
        fp = root / rel
        if not fp.is_file():
            missing.append(rel)
            continue
        actual = sha256_file(fp)
        if actual == expected:
            matched.append(rel)
        else:
            mismatched.append(rel)

    seen = set(stored.keys())
    extra: list[str] = []
    if root.is_dir():
        for p in root.rglob("*"):
            if p.is_file() and p != manifest_path:
                rel = str(p.relative_to(root)).replace("\\", "/")
                if rel not in seen:
                    extra.append(rel)

    return {
        "ok": not mismatched and not missing,
        "matched": matched,
        "mismatched": mismatched,
        "missing": missing,
        "extra": extra,
    }

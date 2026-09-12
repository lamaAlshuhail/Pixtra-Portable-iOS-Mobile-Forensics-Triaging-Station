#!/usr/bin/env python3

import argparse
import glob
import os
import plistlib
import sqlite3
import struct
import sys
from datetime import datetime, timezone
from typing import Optional


_THIS = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_THIS)
_CANONICAL_CASES = os.environ.get(
    "PIXTRA_CASE_STORAGE", os.path.join(_BACKEND_ROOT, "data", "cases")
)
_CASES_STORAGE_ROOT = _CANONICAL_CASES


if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


_PROTECTION_CLASS_NAMES = {
    6: "kSecAttrAccessibleWhenUnlocked",
    7: "kSecAttrAccessibleAfterFirstUnlock",
    8: "kSecAttrAccessibleAlways",
    9: "kSecAttrAccessibleWhenUnlockedThisDeviceOnly",
    10: "kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly",
    11: "kSecAttrAccessibleAlwaysThisDeviceOnly",
}
_THIS_DEVICE_ONLY_CLASSES = {9, 10, 11}

_KEYCHAIN_TABLES = ("genp", "inet", "cert", "keys")


def _resolve_paths(case_id: str, acq_id: str) -> tuple[str, str]:
    from app.services.database import get_acquisition, get_case

    acq = get_acquisition(acq_id)
    if not acq:
        raise SystemExit(f"Acquisition {acq_id} not found")
    if acq.get("case_id") != case_id:
        raise SystemExit(
            f"Acquisition {acq_id} belongs to case {acq.get('case_id')}, "
            f"not {case_id}"
        )
    case = get_case(case_id)
    if not case:
        raise SystemExit(f"Case {case_id} not found")

    output_path = acq.get("output_path")
    if not output_path:
        raise SystemExit("Acquisition has no output_path")

    candidate_globs = [
        os.path.join(
            _CASES_STORAGE_ROOT, case_id, "extractions", acq_id,
            "ios_backup", "*", "Manifest.plist",
        ),
        os.path.join(
            _BACKEND_ROOT, "..", "data", "cases", case_id, "extractions",
            acq_id, "ios_backup", "*", "Manifest.plist",
        ),
        os.path.join(output_path, "ios_backup", "*", "Manifest.plist"),
        os.path.join(output_path, "Manifest.plist"),
        os.path.join(output_path, "ios_backup", "Manifest.plist"),
    ]

    backup_dir: Optional[str] = None
    for pattern in candidate_globs:
        matches = sorted(glob.glob(pattern))
        if matches:
            backup_dir = os.path.dirname(matches[0])
            break

    if not backup_dir:
        listed = "\n  ".join(candidate_globs)
        raise SystemExit(
            "Could not find Manifest.plist for "
            f"case={case_id} acquisition={acq_id}. Searched:\n  {listed}"
        )

    _legacy_cases = os.path.join(_BACKEND_ROOT, "data", "cases")
    case_storage_candidates = [
        os.environ.get("PIXTRA_CASE_STORAGE"),
        _CANONICAL_CASES,
        _legacy_cases,
    ]
    artifacts_db: Optional[str] = None
    for candidate_root in case_storage_candidates:
        if not candidate_root:
            continue
        path = os.path.join(candidate_root, case_id, "artifacts.db")
        if os.path.isfile(path):
            artifacts_db = path
            break
    if not artifacts_db:
        listed = "\n  ".join(
            os.path.join(c, case_id, "artifacts.db")
            for c in case_storage_candidates if c
        )
        raise SystemExit(
            f"artifacts.db not found for case={case_id}. Tried:\n  {listed}"
        )

    return backup_dir, artifacts_db


def _load_keychain_plist(backup_dir: str, passphrase: str) -> bytes:
    try:
        from iphone_backup_decrypt import EncryptedBackup, RelativePath
    except ImportError as exc:
        raise SystemExit(
            "iphone_backup_decrypt is not installed in this Python "
            "environment. Run from the keychain-venv on the Pi."
        ) from exc

    backup = EncryptedBackup(backup_directory=backup_dir, passphrase=passphrase)
    backup.test_decryption()
    return backup.extract_file_as_bytes(
        relative_path="keychain-backup.plist",
        domain_like="KeychainDomain",
    )


def _read_lockdown_versions(backup_dir: str) -> tuple[Optional[str], Optional[str]]:
    manifest_plist = os.path.join(backup_dir, "Manifest.plist")
    try:
        with open(manifest_plist, "rb") as fh:
            mp = plistlib.load(fh)
    except (OSError, plistlib.InvalidFileException):
        return None, None
    lockdown = mp.get("Lockdown") or {}
    return lockdown.get("ProductVersion"), lockdown.get("ProductType")


def _parse_persistent_ref(blob) -> tuple[Optional[str], Optional[str]]:
    if not isinstance(blob, (bytes, bytearray)) or len(blob) < 20:
        return None, None
    try:
        tag = blob[:4].decode("ascii", errors="replace")
    except Exception:
        tag = None
    uuid_bytes = bytes(blob[4:20])
    uuid_str = (
        f"{uuid_bytes[0:4].hex()}-{uuid_bytes[4:6].hex()}-"
        f"{uuid_bytes[6:8].hex()}-{uuid_bytes[8:10].hex()}-"
        f"{uuid_bytes[10:16].hex()}"
    )
    return tag, uuid_str


def _parse_v_data_header(blob) -> tuple[Optional[int], Optional[bytes]]:
    if not isinstance(blob, (bytes, bytearray)) or len(blob) < 12:
        return None, None
    try:
        _version, prot_class, wkey_len = struct.unpack_from("<III", blob, 0)
    except struct.error:
        return None, None
    if wkey_len <= 0 or 12 + wkey_len > len(blob):
        return prot_class, None
    return prot_class, bytes(blob[12:12 + wkey_len])


def _ensure_schema(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(keychain_items)")
    existing_cols = {row[1] for row in cur.fetchall()}
    NEW_REQUIRED = {
        "table_name", "item_uuid", "protection_class", "wrapped_key_hex",
    }
    if existing_cols and not NEW_REQUIRED.issubset(existing_cols):
        print(
            "[parse_keychain] migrating old keychain_items schema "
            "→ dropping and recreating"
        )
        conn.execute("DROP TABLE IF EXISTS keychain_items")
        conn.execute("DROP TABLE IF EXISTS keychain_meta")
        conn.commit()

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS keychain_items (
          id INTEGER PRIMARY KEY,
          acquisition_id TEXT,
          table_name TEXT,
          item_uuid TEXT,
          protection_class INTEGER,
          protection_class_name TEXT,
          is_this_device_only INTEGER,
          v_data_size INTEGER,
          wrapped_key_hex TEXT,
          decrypted INTEGER DEFAULT 0,
          service TEXT,
          account TEXT,
          agrp TEXT,
          value TEXT
        );

        CREATE TABLE IF NOT EXISTS keychain_meta (
          acquisition_id TEXT PRIMARY KEY,
          keybag_uuid TEXT,
          ios_version TEXT,
          device_type TEXT,
          total_items INTEGER,
          parsed_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_keychain_items_acq
          ON keychain_items(acquisition_id);
        CREATE INDEX IF NOT EXISTS idx_keychain_items_table
          ON keychain_items(table_name);
        CREATE INDEX IF NOT EXISTS idx_keychain_items_class
          ON keychain_items(protection_class);
        """
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--case", required=True, help="Case id")
    parser.add_argument("--acquisition", required=True, help="Acquisition id")
    parser.add_argument(
        "--passphrase", default=None,
        help="iTunes backup passphrase (defaults to the value stored on "
             "the acquisition row in pixtra.db)",
    )
    args = parser.parse_args()

    backup_dir, artifacts_db = _resolve_paths(args.case, args.acquisition)
    print(f"[parse_keychain] backup dir: {backup_dir}")
    print(f"[parse_keychain] artifacts.db: {artifacts_db}")

    passphrase = args.passphrase or os.environ.get("PIXTRA_BACKUP_PASSPHRASE")
    if not passphrase:
        from app.services.database import get_acquisition_secret
        passphrase = get_acquisition_secret(args.acquisition, "backup_passphrase")
    if not passphrase:
        raise SystemExit(
            "No backup passphrase available: pass --passphrase, set "
            "PIXTRA_BACKUP_PASSPHRASE, or run the acquisition through Pixtra."
        )

    plist_bytes = _load_keychain_plist(backup_dir, passphrase)
    kc = plistlib.loads(plist_bytes)

    keybag_uuid = kc.get("keybag-uuid")
    if isinstance(keybag_uuid, bytes):
        try:
            keybag_uuid = keybag_uuid.decode("utf-8", errors="replace")
        except Exception:
            keybag_uuid = None

    ios_version, device_type = _read_lockdown_versions(backup_dir)

    counts = {t: 0 for t in _KEYCHAIN_TABLES}
    rows: list[tuple] = []
    for table in _KEYCHAIN_TABLES:
        items = kc.get(table) or []
        for entry in items:
            v_data = entry.get("v_Data")
            v_pref = entry.get("v_PersistentRef")
            tag, uuid_str = _parse_persistent_ref(v_pref)
            prot_class, wrapped_key = _parse_v_data_header(v_data)
            v_size = len(v_data) if isinstance(v_data, (bytes, bytearray)) else 0
            wrapped_hex = wrapped_key.hex() if wrapped_key else None
            cls_name = _PROTECTION_CLASS_NAMES.get(prot_class) if prot_class is not None else None
            is_tdo = 1 if (prot_class in _THIS_DEVICE_ONLY_CLASSES) else 0
            counts[table] += 1
            rows.append((
                args.acquisition,
                tag or table,
                uuid_str,
                prot_class,
                cls_name,
                is_tdo,
                v_size,
                wrapped_hex,
                0,
                None,
                None,
                None,
                None,
            ))

    total = sum(counts.values())
    parsed_at = datetime.now(tz=timezone.utc).isoformat()

    conn = sqlite3.connect(artifacts_db)
    try:
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)
        conn.execute(
            "DELETE FROM keychain_items WHERE acquisition_id = ?",
            (args.acquisition,),
        )
        conn.executemany(
            """
            INSERT INTO keychain_items (
              acquisition_id, table_name, item_uuid,
              protection_class, protection_class_name, is_this_device_only,
              v_data_size, wrapped_key_hex, decrypted,
              service, account, agrp, value
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.execute(
            """
            INSERT INTO keychain_meta (
              acquisition_id, keybag_uuid, ios_version, device_type,
              total_items, parsed_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(acquisition_id) DO UPDATE SET
              keybag_uuid=excluded.keybag_uuid,
              ios_version=excluded.ios_version,
              device_type=excluded.device_type,
              total_items=excluded.total_items,
              parsed_at=excluded.parsed_at
            """,
            (
                args.acquisition,
                keybag_uuid,
                ios_version,
                device_type,
                total,
                parsed_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    print(
        f"Parsed {total:,} items: "
        + ", ".join(f"{t}={counts[t]}" for t in _KEYCHAIN_TABLES)
    )
    print(f"keybag-uuid: {keybag_uuid}")
    print(f"iOS version: {ios_version}  device: {device_type}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

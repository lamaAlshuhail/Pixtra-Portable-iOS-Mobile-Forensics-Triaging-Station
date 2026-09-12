#!/usr/bin/env python3

import os
import shutil
import sqlite3
import sys


CASE_ID = "YOUR_CASE_ID"
ACQUISITION_ID = "YOUR_ACQUISITION_ID"
ADDRESSBOOK_PATH = (
    "/path/to/decrypted/backup/HomeDomain/Library/AddressBook"
    "/AddressBook.sqlitedb"
)
ARTIFACTS_DB = "/path/to/cases/YOUR_CASE_ID/artifacts.db"
PIXTRA_DB = os.environ.get(
    "PIXTRA_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "pixtra.db"),
)


_THIS = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_THIS)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

try:
    from app.services.parser_engine import ArtifactsDB, ContactsParser
except ImportError as exc:
    print(
        f"ERROR: could not import parser_engine ({exc}). "
        f"Run from a checkout where pixtra-backend/app/ is intact, "
        f"or set PYTHONPATH to {_BACKEND_ROOT}.",
        file=sys.stderr,
    )
    sys.exit(1)


def _lookup_device_id() -> "str | None":
    if not os.path.isfile(PIXTRA_DB):
        print(
            f"WARNING: pixtra.db not found at {PIXTRA_DB} - "
            "device_id will be NULL on backfilled rows.",
            file=sys.stderr,
        )
        return None
    try:
        pdb = sqlite3.connect(PIXTRA_DB)
        try:
            row = pdb.execute(
                "SELECT device_id FROM acquisitions WHERE id = ?",
                (ACQUISITION_ID,),
            ).fetchone()
        finally:
            pdb.close()
    except sqlite3.Error as exc:
        print(
            f"WARNING: pixtra.db lookup failed: {exc} - device_id will be NULL.",
            file=sys.stderr,
        )
        return None
    if not row:
        print(
            f"WARNING: no acquisitions row for id={ACQUISITION_ID!r} - "
            "device_id will be NULL.",
            file=sys.stderr,
        )
        return None
    return row[0]


def main() -> int:
    if not os.path.isfile(ARTIFACTS_DB):
        print(f"ERROR: artifacts.db not found at {ARTIFACTS_DB}", file=sys.stderr)
        return 1
    if not os.path.isfile(ADDRESSBOOK_PATH):
        print(
            f"ERROR: AddressBook.sqlitedb not found at {ADDRESSBOOK_PATH}",
            file=sys.stderr,
        )
        return 1

    backup_path = ARTIFACTS_DB + ".before-contacts-backfill"
    print(f"[contacts] Backing up {ARTIFACTS_DB}")
    print(f"[contacts]            -> {backup_path}")
    shutil.copy2(ARTIFACTS_DB, backup_path)

    device_id = _lookup_device_id()
    print(f"[contacts] device_id = {device_id!r}")

    case_dir = os.path.dirname(ARTIFACTS_DB)
    artifacts = ArtifactsDB(case_dir)
    try:
        parser = ContactsParser()
        count = parser.parse(
            ADDRESSBOOK_PATH, artifacts, device_id, ACQUISITION_ID
        )
    finally:
        artifacts.close()

    print(
        f"[contacts] Imported {count} contacts from AddressBook.sqlitedb"
    )
    print(
        "[contacts] If something looks wrong, restore with: "
        f"cp {backup_path} {ARTIFACTS_DB}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

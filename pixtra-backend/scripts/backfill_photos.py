#!/usr/bin/env python3

import json
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


CASE_ID = "YOUR_CASE_ID"
ACQUISITION_ID = "YOUR_ACQUISITION_ID"
CAMERA_ROLL_PATH = "/path/to/decrypted/backup/CameraRollDomain"
ARTIFACTS_DB = "/path/to/cases/YOUR_CASE_ID/artifacts.db"
PIXTRA_DB = os.environ.get(
    "PIXTRA_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "pixtra.db"),
)

IMAGE_EXTS = {".jpg", ".jpeg", ".heic", ".heif"}
MIN_BYTES = 10240
SKIP_DIR_NAMES = {"Thumbnails", "Caches"}
BATCH_SIZE = 500


try:
    from PIL import ExifTags, Image
except ImportError:
    print("ERROR: Pillow not installed. Run: pip install Pillow", file=sys.stderr)
    sys.exit(1)

HEIC_OK = True
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    HEIC_OK = False
    print(
        "WARNING: pillow-heif not installed - HEIC/HEIF files will be skipped. "
        "Install with: pip install pillow-heif",
        file=sys.stderr,
    )


def _ratio_to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            num, den = value
            return num / den if den else None
        except Exception:
            return None


def _gps_to_decimal(coord, ref):
    if not coord or len(coord) < 3:
        return None
    try:
        d = _ratio_to_float(coord[0]) or 0.0
        m = _ratio_to_float(coord[1]) or 0.0
        s = _ratio_to_float(coord[2]) or 0.0
        decimal = d + m / 60.0 + s / 3600.0
        if ref in ("S", "W"):
            decimal = -decimal
        return decimal
    except Exception:
        return None


def _read_exif(fpath: str) -> dict:
    out = {
        "timestamp_iso": None,
        "timestamp_unix": 0.0,
        "latitude": None,
        "longitude": None,
        "altitude": None,
        "make": None,
        "model": None,
    }
    try:
        with Image.open(fpath) as im:
            exif = im.getexif()
            if not exif:
                return out
            tagged = {ExifTags.TAGS.get(t, t): exif.get(t) for t in exif}

            dt_str = tagged.get("DateTimeOriginal") or tagged.get("DateTime")
            if dt_str:
                try:
                    dt = datetime.strptime(str(dt_str), "%Y:%m:%d %H:%M:%S")
                    dt = dt.replace(tzinfo=timezone.utc)
                    out["timestamp_iso"] = dt.isoformat()
                    out["timestamp_unix"] = dt.timestamp()
                except (ValueError, TypeError):
                    pass

            make = tagged.get("Make")
            model = tagged.get("Model")
            out["make"] = str(make).strip() if make else None
            out["model"] = str(model).strip() if model else None

            gps = None
            try:
                gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
            except (AttributeError, KeyError):
                gps = exif.get(0x8825) or {}
            if gps:
                gps_named = {ExifTags.GPSTAGS.get(t, t): gps.get(t) for t in gps}
                out["latitude"] = _gps_to_decimal(
                    gps_named.get("GPSLatitude"),
                    gps_named.get("GPSLatitudeRef"),
                )
                out["longitude"] = _gps_to_decimal(
                    gps_named.get("GPSLongitude"),
                    gps_named.get("GPSLongitudeRef"),
                )
                out["altitude"] = _ratio_to_float(gps_named.get("GPSAltitude"))
    except Exception:
        pass
    return out


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
    if not os.path.isdir(CAMERA_ROLL_PATH):
        print(
            f"ERROR: CameraRoll not found at {CAMERA_ROLL_PATH}",
            file=sys.stderr,
        )
        return 1

    backup_path = ARTIFACTS_DB + ".before-backfill"
    print(f"[backfill] Backing up {ARTIFACTS_DB}")
    print(f"[backfill]            -> {backup_path}")
    shutil.copy2(ARTIFACTS_DB, backup_path)

    device_id = _lookup_device_id()
    print(f"[backfill] device_id = {device_id!r}")

    rel_base = os.path.dirname(os.path.normpath(CAMERA_ROLL_PATH))

    print(f"[backfill] Counting files under {CAMERA_ROLL_PATH}...")
    candidates: "list[str]" = []
    for root, _dirs, files in os.walk(CAMERA_ROLL_PATH):
        if any(part in SKIP_DIR_NAMES for part in Path(root).parts):
            continue
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in IMAGE_EXTS:
                candidates.append(os.path.join(root, fname))
    total = len(candidates)
    print(f"[backfill] Found {total} candidate image files")

    conn = sqlite3.connect(ARTIFACTS_DB)
    cur = conn.cursor()

    processed = 0
    indexed = 0
    no_exif = 0
    too_small = 0
    skipped_heic = 0
    t0 = time.time()

    for fpath in candidates:
        processed += 1
        try:
            size = os.path.getsize(fpath)
        except OSError:
            continue

        if size < MIN_BYTES:
            too_small += 1
            continue

        ext = os.path.splitext(fpath)[1].lower()
        if ext in {".heic", ".heif"} and not HEIC_OK:
            skipped_heic += 1
            continue

        rel_path = os.path.relpath(fpath, rel_base)
        fname = os.path.basename(fpath)

        exif = _read_exif(fpath)
        ts_iso = exif["timestamp_iso"]
        ts_unix = exif["timestamp_unix"]
        used_mtime = False
        if not ts_iso:
            no_exif += 1
            try:
                mtime = os.path.getmtime(fpath)
                ts_unix = float(mtime)
                ts_iso = (
                    datetime.utcfromtimestamp(mtime)
                    .replace(tzinfo=timezone.utc)
                    .isoformat()
                )
                used_mtime = True
            except OSError:
                ts_iso = None
                ts_unix = 0.0

        meta = {
            "file": rel_path,
            "altitude": exif.get("altitude"),
            "make": exif.get("make"),
            "model": exif.get("model"),
        }
        if used_mtime:
            meta["timestamp_source"] = "mtime"

        cur.execute(
            """INSERT INTO locations (
                source, latitude, longitude, altitude,
                timestamp, timestamp_unix, label, metadata,
                device_id, acquisition_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "exif",
                exif["latitude"],
                exif["longitude"],
                exif["altitude"],
                ts_iso,
                ts_unix,
                fname,
                json.dumps(meta),
                device_id,
                ACQUISITION_ID,
            ),
        )
        loc_id = cur.lastrowid

        if ts_iso is not None and ts_unix:
            if exif["latitude"] is not None and exif["longitude"] is not None:
                desc = f"GPS: {exif['latitude']:.5f}, {exif['longitude']:.5f}"
            else:
                desc = rel_path
            cur.execute(
                """INSERT INTO timeline_events (
                    event_type, timestamp, timestamp_unix,
                    title, description,
                    source_table, source_id,
                    device_id, acquisition_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "photo",
                    ts_iso,
                    ts_unix,
                    f"Photo: {fname}",
                    desc,
                    "locations",
                    loc_id,
                    device_id,
                    ACQUISITION_ID,
                ),
            )

        indexed += 1

        if processed % BATCH_SIZE == 0:
            conn.commit()
            elapsed = time.time() - t0
            rate = processed / elapsed if elapsed > 0 else 0.0
            remaining = (total - processed) / rate if rate > 0 else 0.0
            print(
                f"[backfill] {processed} of ~{total} processed, "
                f"{indexed} indexed "
                f"({no_exif} no EXIF, {too_small} too small) "
                f"ETA: {int(remaining / 60)}m"
            )

    conn.commit()
    conn.close()

    elapsed = time.time() - t0
    print()
    print(f"[backfill] Done in {int(elapsed / 60)}m {int(elapsed % 60)}s")
    print(
        f"[backfill] processed={processed} indexed={indexed} "
        f"no_exif={no_exif} too_small={too_small} skipped_heic={skipped_heic}"
    )
    print(
        "[backfill] If something looks wrong, restore with: "
        f"cp {backup_path} {ARTIFACTS_DB}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

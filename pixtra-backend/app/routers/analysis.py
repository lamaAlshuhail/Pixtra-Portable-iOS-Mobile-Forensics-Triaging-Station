import json
import logging
import math
import os
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.routers.auth import require_role
from app.services.database import get_case, get_acquisition, log_custody
from app.services.database import case_dir as case_dir_for
from app.services.parser_engine import parse_extraction, ArtifactsDB
from app.services.entity_extraction import extract_entities, get_entity_graph
from app.models.schemas import CustodyAction

logger = logging.getLogger(__name__)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _humanize_duration(secs: float) -> str:
    if secs < 60:
        return f"{int(secs)}s"
    mins = secs / 60
    if mins < 60:
        return f"{int(mins)}m"
    hours = mins / 60
    if hours < 24:
        h = int(hours)
        m = int(mins - h * 60)
        return f"{h}h {m}m" if m else f"{h}h"
    days = hours / 24
    d = int(days)
    h = int(hours - d * 24)
    return f"{d}d {h}h" if h else f"{d}d"

try:
    from PIL import Image
except ImportError:
    Image = None
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

router = APIRouter()

CASE_STORAGE_ROOT = os.path.abspath(os.environ.get("PIXTRA_CASE_STORAGE", "data/cases"))


def _get_artifacts_conn(case_id: str):
    db_path = os.path.join(case_dir_for(case_id), "artifacts.db")
    if not os.path.exists(db_path):
        return None
    try:
        ArtifactsDB(os.path.dirname(db_path)).conn.close()
    except Exception as e:
        logger.warning(f"Could not ensure artifacts schema for {case_id}: {e}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@router.post("/parse/{acquisition_id}")
async def run_parser(
    acquisition_id: str,
    _: dict = Depends(require_role("examiner", "supervisor")),
):
    acq = get_acquisition(acquisition_id)
    if not acq:
        raise HTTPException(status_code=404, detail="Acquisition not found")
    if acq["status"] != "complete":
        raise HTTPException(status_code=400, detail="Acquisition not complete yet")

    case = get_case(acq["case_id"])
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case_dir = case_dir_for(acq["case_id"])
    extraction_dir = acq["output_path"]

    from app.services.database import get_device
    device = get_device(acq["device_id"])
    platform = device.get("platform", "ios") if device else "ios"

    results = parse_extraction(
        case_dir=case_dir,
        extraction_dir=extraction_dir,
        platform=platform,
        device_id=acq["device_id"],
        acquisition_id=acquisition_id,
    )

    log_custody({
        "id": uuid4().hex[:12],
        "case_id": acq["case_id"],
        "action": CustodyAction.EVIDENCE_ACCESSED.value,
        "examiner": case["examiner"],
        "acquisition_id": acquisition_id,
        "details": f"Parser engine executed: {results}",
    })

    return {"parsed": results}


@router.post("/entities/{case_id}")
async def build_entity_graph(
    case_id: str,
    _: dict = Depends(require_role("examiner", "supervisor")),
):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case_dir = case_dir_for(case_id)
    results = extract_entities(case_dir)
    return results


@router.get("/evidence/{case_id}")
async def get_evidence_categories(case_id: str):
    conn = _get_artifacts_conn(case_id)
    if not conn:
        return {
            "case_id": case_id,
            "categories": {},
            "total_artifacts": 0,
            "message": "No parsed artifacts yet - run /api/analysis/parse/{acquisition_id} first",
        }

    try:
        counts = {}
        for table in ["messages", "contacts", "calls", "locations",
                       "web_history", "wifi_networks", "keychain_items",
                       "ai_conversations"]:
            try:
                row = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()
                counts[table] = row["c"]
            except sqlite3.OperationalError:
                counts[table] = 0

        try:
            row = conn.execute(
                "SELECT COUNT(*) as c FROM sim_scans"
            ).fetchone()
            counts["sim_scan_count"] = row["c"]
        except sqlite3.OperationalError:
            counts["sim_scan_count"] = 0

        counts["installed_apps"] = 0
        try:
            from app.services.database import list_acquisitions
            acqs = list_acquisitions(case_id)
            for acq in acqs:
                output_path = acq.get("output_path")
                if not output_path:
                    continue
                app_db = os.path.join(output_path, _APPS_REL)
                if not os.path.isfile(app_db):
                    continue
                appconn = sqlite3.connect(app_db)
                try:
                    row = appconn.execute(
                        "SELECT COUNT(DISTINCT application_identifier) "
                        "FROM application_identifier_tab"
                    ).fetchone()
                    counts["installed_apps"] = row[0] if row else 0
                    break
                except sqlite3.OperationalError:
                    pass
                finally:
                    appconn.close()
        except Exception as exc:
            logger.warning("installed_apps count failed: %s", exc)

        msg_sources = {}
        try:
            for row in conn.execute(
                "SELECT source, COUNT(*) as c FROM messages GROUP BY source"
            ).fetchall():
                msg_sources[row["source"]] = row["c"]
        except sqlite3.OperationalError:
            pass

        photos = 0
        try:
            row = conn.execute(
                "SELECT COUNT(*) as c FROM timeline_events WHERE event_type = 'photo'"
            ).fetchone()
            photos = row["c"] if row else 0
        except sqlite3.OperationalError:
            pass

        total = sum(counts.values())
        return {
            "case_id": case_id,
            "categories": counts,
            "message_sources": msg_sources,
            "photos": photos,
            "total_artifacts": total,
        }
    finally:
        conn.close()


@router.get("/evidence/{case_id}/messages")
async def get_messages(
    case_id: str,
    source: Optional[str] = None,
    chat_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
):
    conn = _get_artifacts_conn(case_id)
    if not conn:
        raise HTTPException(status_code=404, detail="No parsed artifacts")

    try:
        query = "SELECT * FROM messages WHERE 1=1"
        params = []

        if source:
            query += " AND source = ?"
            params.append(source)
        if chat_id:
            query += " AND chat_id = ?"
            params.append(chat_id)
        if search:
            query += " AND text LIKE ?"
            params.append(f"%{search}%")

        query += " ORDER BY timestamp_unix ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/evidence/{case_id}/chats")
async def get_chat_list(
    case_id: str,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    source: Optional[str] = None,
):
    conn = _get_artifacts_conn(case_id)
    if not conn:
        raise HTTPException(status_code=404, detail="No parsed artifacts")

    try:
        where = ["chat_id IS NOT NULL"]
        params: list = []
        if source:
            where.append("source = ?")
            params.append(source)
        where_clause = " AND ".join(where)

        total = conn.execute(
            f"SELECT COUNT(DISTINCT chat_id || ':' || source) AS c "
            f"FROM messages WHERE {where_clause}",
            params,
        ).fetchone()["c"]

        rows = conn.execute(
            f"""
            SELECT chat_id, chat_name, source,
                   COUNT(*) as message_count,
                   MIN(timestamp) as first_message,
                   MAX(timestamp) as last_message,
                   SUM(is_deleted) as deleted_count
            FROM messages
            WHERE {where_clause}
            GROUP BY chat_id, source
            ORDER BY MAX(timestamp_unix) DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()

        return {
            "chats": [dict(r) for r in rows],
            "total": int(total or 0),
            "limit": limit,
            "offset": offset,
        }
    finally:
        conn.close()


@router.get("/evidence/{case_id}/contacts")
async def get_contacts(case_id: str, search: Optional[str] = None):
    conn = _get_artifacts_conn(case_id)
    if not conn:
        raise HTTPException(status_code=404, detail="No parsed artifacts")

    try:
        if search:
            rows = conn.execute(
                "SELECT * FROM contacts WHERE name LIKE ? OR phone LIKE ? OR email LIKE ?",
                (f"%{search}%", f"%{search}%", f"%{search}%"),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM contacts ORDER BY name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/evidence/{case_id}/wifi")
async def get_wifi_networks(case_id: str):
    conn = _get_artifacts_conn(case_id)
    if not conn:
        raise HTTPException(status_code=404, detail="No parsed artifacts")

    try:
        rows = conn.execute(
            "SELECT * FROM wifi_networks ORDER BY last_joined_unix DESC"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            meta = {}
            if d.get("metadata"):
                try:
                    meta = json.loads(d["metadata"])
                except (TypeError, ValueError):
                    meta = {}
            d["security"] = meta.get("security", "")
            d["last_connected"] = d.get("last_joined")
            out.append(d)
        return out
    finally:
        conn.close()


@router.get("/evidence/{case_id}/calls")
async def get_calls(case_id: str, direction: Optional[str] = None):
    conn = _get_artifacts_conn(case_id)
    if not conn:
        raise HTTPException(status_code=404, detail="No parsed artifacts")

    try:
        if direction:
            rows = conn.execute(
                "SELECT * FROM calls WHERE direction = ? ORDER BY timestamp_unix DESC",
                (direction,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM calls ORDER BY timestamp_unix DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/evidence/{case_id}/locations")
async def get_locations(case_id: str):
    conn = _get_artifacts_conn(case_id)
    if not conn:
        raise HTTPException(status_code=404, detail="No parsed artifacts")

    try:
        rows = conn.execute(
            """
            SELECT l.id, l.source, l.latitude, l.longitude, l.altitude,
                   l.accuracy,
                   l.timestamp, l.timestamp_unix, l.label, l.metadata,
                   l.device_id, l.acquisition_id,
                   te.id AS photo_id
            FROM locations l
            LEFT JOIN timeline_events te
                   ON te.source_id = l.id
                  AND te.source_table = 'locations'
                  AND te.event_type = 'photo'
            WHERE l.latitude IS NOT NULL AND l.longitude IS NOT NULL
            ORDER BY l.timestamp_unix DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


_FREQUENT_RADIUS_KM = 0.2
_FREQUENT_MIN_NEIGHBOURS = 2


@router.get("/evidence/{case_id}/dwell-points")
async def get_dwell_points(
    case_id: str,
    min_dwell_minutes: int = Query(30, ge=1),
    radius_meters: float = Query(100.0, gt=0),
):
    conn = _get_artifacts_conn(case_id)
    if not conn:
        raise HTTPException(status_code=404, detail="No parsed artifacts")

    try:
        rows = conn.execute(
            """
            SELECT id, latitude, longitude, timestamp_unix, timestamp, label
            FROM locations
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
              AND source = 'exif'
            ORDER BY timestamp_unix ASC
            """
        ).fetchall()
    finally:
        conn.close()

    radius_km = radius_meters / 1000.0
    min_dwell_seconds = min_dwell_minutes * 60

    cluster: list[dict] = []
    centroid_lat = 0.0
    centroid_lon = 0.0
    last_unix: Optional[int] = None
    stay_points: list[dict] = []

    def _emit_cluster(points: list[dict]) -> None:
        if len(points) < 2:
            return
        first_unix = points[0]["timestamp_unix"]
        last_pt_unix = points[-1]["timestamp_unix"]
        if first_unix is None or last_pt_unix is None:
            return
        duration = last_pt_unix - first_unix
        if duration < min_dwell_seconds:
            return
        c_lat = sum(p["latitude"] for p in points) / len(points)
        c_lon = sum(p["longitude"] for p in points) / len(points)
        stay_points.append({
            "id": len(stay_points) + 1,
            "centroid_lat": c_lat,
            "centroid_lon": c_lon,
            "arrived": points[0]["timestamp"],
            "departed": points[-1]["timestamp"],
            "_arrived_unix": first_unix,
            "_departed_unix": last_pt_unix,
            "duration_seconds": int(duration),
            "duration_human": _humanize_duration(duration),
            "photo_count": len(points),
            "is_frequent": False,
        })

    for r in rows:
        ts = r["timestamp_unix"]
        if ts is None:
            continue
        if last_unix is not None and ts < last_unix:
            logger.warning(
                "Skipping out-of-order locations row id=%s ts=%s (last=%s)",
                r["id"], ts, last_unix,
            )
            continue
        last_unix = ts
        lat = r["latitude"]
        lon = r["longitude"]
        if not cluster:
            cluster = [{
                "id": r["id"],
                "latitude": lat,
                "longitude": lon,
                "timestamp": r["timestamp"],
                "timestamp_unix": ts,
            }]
            centroid_lat = lat
            centroid_lon = lon
            continue
        dist = _haversine_km(centroid_lat, centroid_lon, lat, lon)
        if dist <= radius_km:
            cluster.append({
                "id": r["id"],
                "latitude": lat,
                "longitude": lon,
                "timestamp": r["timestamp"],
                "timestamp_unix": ts,
            })
            n = len(cluster)
            centroid_lat = ((centroid_lat * (n - 1)) + lat) / n
            centroid_lon = ((centroid_lon * (n - 1)) + lon) / n
        else:
            _emit_cluster(cluster)
            cluster = [{
                "id": r["id"],
                "latitude": lat,
                "longitude": lon,
                "timestamp": r["timestamp"],
                "timestamp_unix": ts,
            }]
            centroid_lat = lat
            centroid_lon = lon
    _emit_cluster(cluster)

    for i, sp in enumerate(stay_points):
        neighbours = 0
        for j, other in enumerate(stay_points):
            if i == j:
                continue
            d = _haversine_km(
                sp["centroid_lat"], sp["centroid_lon"],
                other["centroid_lat"], other["centroid_lon"],
            )
            if d <= _FREQUENT_RADIUS_KM:
                neighbours += 1
                if neighbours >= _FREQUENT_MIN_NEIGHBOURS:
                    break
        sp["is_frequent"] = neighbours >= _FREQUENT_MIN_NEIGHBOURS

    trips: list[dict] = []
    for prev, nxt in zip(stay_points, stay_points[1:]):
        dist_km = _haversine_km(
            prev["centroid_lat"], prev["centroid_lon"],
            nxt["centroid_lat"], nxt["centroid_lon"],
        )
        duration = nxt["_arrived_unix"] - prev["_departed_unix"]
        avg_speed = None
        if duration > 0:
            avg_speed = dist_km / (duration / 3600.0)
        trips.append({
            "from_stay_id": prev["id"],
            "to_stay_id": nxt["id"],
            "departed": prev["departed"],
            "arrived": nxt["arrived"],
            "distance_km": round(dist_km, 2),
            "duration_seconds": int(max(duration, 0)),
            "duration_human": _humanize_duration(max(duration, 0)),
            "avg_speed_kmh": round(avg_speed, 1) if avg_speed is not None else None,
        })

    for sp in stay_points:
        sp.pop("_arrived_unix", None)
        sp.pop("_departed_unix", None)

    total_dwell_seconds = sum(sp["duration_seconds"] for sp in stay_points)
    frequent_count = sum(1 for sp in stay_points if sp["is_frequent"])

    return {
        "stay_points": stay_points,
        "trips": trips,
        "stats": {
            "total_stay_points": len(stay_points),
            "total_trips": len(trips),
            "total_dwell_hours": round(total_dwell_seconds / 3600.0, 1),
            "frequent_locations": frequent_count,
        },
    }


_PASSES_REL = os.path.join("HomeDomain", "Library", "Passes", "Cards")


def _detect_pass_type(pj: dict) -> str:
    if "boardingPass" in pj:
        return "boarding_pass"
    if "eventTicket" in pj:
        return "event_ticket"
    if "coupon" in pj:
        return "coupon"
    if "storeCard" in pj:
        return "store_card"
    return "generic"


_BOARDING_KEY_MAP = {
    "origin": "origin",
    "destination": "destination",
    "passenger-name": "passenger_name",
    "passenger_name": "passenger_name",
    "flight": "flight_number",
    "flight-number": "flight_number",
    "flightnumber": "flight_number",
    "gate": "gate",
    "seat": "seat",
    "boarding-group": "group",
    "group": "group",
    "departure": "departure_date",
    "departure-date": "departure_date",
    "depart": "departure_date",
    "date": "departure_date",
}


def _iter_pass_fields(struct: dict):
    for arr_key in ("primaryFields", "secondaryFields", "auxiliaryFields", "headerFields", "backFields"):
        for f in struct.get(arr_key) or []:
            k = (f.get("key") or "").strip()
            v = f.get("value")
            if k and v is not None:
                yield k, v


def _extract_pass_fields(pj: dict, pass_type: str) -> dict:
    body = (
        pj.get("boardingPass") or pj.get("eventTicket")
        or pj.get("coupon") or pj.get("storeCard") or pj.get("generic")
        or {}
    )
    if pass_type == "boarding_pass":
        out: dict[str, str] = {}
        for k, v in _iter_pass_fields(body):
            normalized = _BOARDING_KEY_MAP.get(k.lower())
            if normalized:
                out.setdefault(normalized, str(v))
        return out
    return {k: str(v) for k, v in _iter_pass_fields(body)}


def _pkpass_dir_size(pkpass_path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(pkpass_path):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass
    return total


@router.get("/evidence/{case_id}/wallet-passes")
async def get_wallet_passes(case_id: str):
    from app.services.database import list_acquisitions

    acqs = list_acquisitions(case_id)
    if not acqs:
        raise HTTPException(status_code=404, detail="No acquisitions for case")

    passes: list[dict] = []
    by_type: dict[str, int] = {
        "boarding_pass": 0, "event_ticket": 0,
        "coupon": 0, "store_card": 0, "generic": 0,
    }

    for acq in acqs:
        output_path = acq.get("output_path")
        if not output_path or not os.path.isdir(output_path):
            continue
        passes_root = os.path.join(output_path, _PASSES_REL)
        if not os.path.isdir(passes_root):
            continue

        for entry in sorted(os.listdir(passes_root)):
            pkpass_dir = os.path.join(passes_root, entry)
            if not os.path.isdir(pkpass_dir):
                continue
            pass_json = os.path.join(pkpass_dir, "pass.json")
            if not os.path.isfile(pass_json):
                continue
            try:
                with open(pass_json, "r", encoding="utf-8") as fh:
                    pj = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Skipping malformed pass.json at %s: %s", pass_json, exc)
                continue

            pass_type = _detect_pass_type(pj)
            by_type[pass_type] = by_type.get(pass_type, 0) + 1

            barcode_format = None
            barcode_message = None
            barcodes = pj.get("barcodes") or ([pj["barcode"]] if pj.get("barcode") else [])
            if barcodes:
                bc = barcodes[0] or {}
                barcode_format = bc.get("format")
                msg = bc.get("message")
                if isinstance(msg, str):
                    barcode_message = msg[:100]

            serial = pj.get("serialNumber") or ""
            if isinstance(serial, str) and len(serial) > 60:
                serial = serial[:60]

            passes.append({
                "id": len(passes) + 1,
                "pass_type": pass_type,
                "organization_name": pj.get("organizationName") or "",
                "description": pj.get("description") or "",
                "serial_number": serial,
                "relevant_date": pj.get("relevantDate"),
                "expiration_date": pj.get("expirationDate"),
                "fields": _extract_pass_fields(pj, pass_type),
                "barcode_format": barcode_format,
                "barcode_message": barcode_message,
                "logo_text": pj.get("logoText") or "",
                "background_color": pj.get("backgroundColor") or "",
                "foreground_color": pj.get("foregroundColor") or "",
                "file_size": _pkpass_dir_size(pkpass_dir),
                "pkpass_dir": os.path.relpath(pkpass_dir, output_path).replace("\\", "/"),
            })

    return {
        "passes": passes,
        "stats": {
            "total_passes": len(passes),
            "by_type": by_type,
        },
    }


_CALENDAR_REL = os.path.join("HomeDomain", "Library", "Calendar", "Calendar.sqlitedb")
_MAC_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)


def _mac_to_iso(mac_secs) -> Optional[str]:
    if mac_secs is None:
        return None
    try:
        return (_MAC_EPOCH + timedelta(seconds=float(mac_secs))).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _calendar_color_to_hex(raw) -> Optional[str]:
    if raw is None:
        return None
    if isinstance(raw, int):
        return f"#{raw & 0xFFFFFF:06X}"
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8", errors="replace")
        except Exception:
            return None
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("#") and len(s) in (4, 7):
            return s
        parts = s.split()
        if len(parts) >= 3:
            try:
                rgb = [max(0, min(255, int(round(float(p) * 255)))) for p in parts[:3]]
                return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"
            except ValueError:
                return None
    return None


@router.get("/evidence/{case_id}/calendar-events")
async def get_calendar_events(
    case_id: str,
    search: Optional[str] = None,
    calendar_id: Optional[int] = None,
):
    from app.services.database import list_acquisitions

    acqs = list_acquisitions(case_id)
    if not acqs:
        raise HTTPException(status_code=404, detail="No acquisitions for case")

    db_path: Optional[str] = None
    for acq in acqs:
        output_path = acq.get("output_path")
        if not output_path:
            continue
        candidate = os.path.join(output_path, _CALENDAR_REL)
        if os.path.isfile(candidate):
            db_path = candidate
            break

    if not db_path:
        return {
            "events": [],
            "calendars": [],
            "stats": {
                "total_events": 0,
                "by_calendar": {},
                "date_range": {"earliest": None, "latest": None},
            },
        }

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cal_cols = [
            r[1] for r in conn.execute("PRAGMA table_info(Calendar)").fetchall()
        ]
        acct_col = "subcal_account_id" if "subcal_account_id" in cal_cols else "account"
        cal_rows = conn.execute(
            f"""
            SELECT c.ROWID AS id, c.title, c.color, c.{acct_col} AS account,
                   COUNT(ci.ROWID) AS event_count
            FROM Calendar c
            LEFT JOIN CalendarItem ci ON ci.calendar_id = c.ROWID
            GROUP BY c.ROWID
            ORDER BY event_count DESC, c.title
            """
        ).fetchall()
        calendars = [
            {
                "id": r["id"],
                "title": r["title"] or "(unnamed)",
                "color_hex": _calendar_color_to_hex(r["color"]),
                "account": r["account"],
                "event_count": int(r["event_count"] or 0),
            }
            for r in cal_rows
        ]

        where: list[str] = []
        params: list = []
        if search:
            like = f"%{search.strip()}%"
            where.append("(LOWER(ci.summary) LIKE LOWER(?) OR LOWER(ci.description) LIKE LOWER(?))")
            params.extend([like, like])
        if calendar_id is not None:
            where.append("ci.calendar_id = ?")
            params.append(calendar_id)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        try:
            ev_rows = conn.execute(
                f"""
                SELECT ci.ROWID AS id, ci.summary, ci.description,
                       ci.start_date, ci.end_date, ci.all_day,
                       ci.status, ci.has_recurrences,
                       ci.UUID, ci.creation_date, ci.last_modified,
                       c.title AS calendar_title, c.color AS calendar_color,
                       l.title AS location_title,
                       l.latitude AS location_lat,
                       l.longitude AS location_lng
                FROM CalendarItem ci
                LEFT JOIN Calendar c ON ci.calendar_id = c.ROWID
                LEFT JOIN Location l ON ci.location_id = l.ROWID
                {where_sql}
                ORDER BY ci.start_date DESC
                """,
                params,
            ).fetchall()
        except sqlite3.OperationalError:
            ev_rows = conn.execute(
                f"""
                SELECT ci.ROWID AS id, ci.summary, ci.description,
                       ci.start_date, ci.end_date, ci.all_day,
                       ci.status, ci.has_recurrences,
                       ci.UUID, ci.creation_date, ci.last_modified,
                       c.title AS calendar_title, c.color AS calendar_color,
                       NULL AS location_title,
                       NULL AS location_lat,
                       NULL AS location_lng
                FROM CalendarItem ci
                LEFT JOIN Calendar c ON ci.calendar_id = c.ROWID
                {where_sql}
                ORDER BY ci.start_date DESC
                """,
                params,
            ).fetchall()
    finally:
        conn.close()

    events: list[dict] = []
    by_calendar: dict[str, int] = {}
    earliest: Optional[float] = None
    latest: Optional[float] = None
    for r in ev_rows:
        sd = r["start_date"]
        ed = r["end_date"]
        try:
            sd_f = float(sd) if sd is not None else None
        except (TypeError, ValueError):
            sd_f = None
        if sd_f is not None:
            if earliest is None or sd_f < earliest:
                earliest = sd_f
            if latest is None or sd_f > latest:
                latest = sd_f
        cal_title = r["calendar_title"] or "(no calendar)"
        by_calendar[cal_title] = by_calendar.get(cal_title, 0) + 1
        events.append({
            "id": r["id"],
            "summary": r["summary"] or "",
            "description": r["description"] or "",
            "start": _mac_to_iso(sd),
            "end": _mac_to_iso(ed),
            "all_day": bool(r["all_day"]),
            "calendar_title": cal_title,
            "calendar_color": _calendar_color_to_hex(r["calendar_color"]),
            "location_title": r["location_title"] or "",
            "location_lat": r["location_lat"],
            "location_lng": r["location_lng"],
            "status": r["status"],
            "has_recurrences": bool(r["has_recurrences"]),
            "uuid": r["UUID"],
            "created": _mac_to_iso(r["creation_date"]),
            "last_modified": _mac_to_iso(r["last_modified"]),
        })

    return {
        "events": events,
        "calendars": calendars,
        "stats": {
            "total_events": len(events),
            "by_calendar": by_calendar,
            "date_range": {
                "earliest": _mac_to_iso(earliest),
                "latest": _mac_to_iso(latest),
            },
        },
    }


_APPS_REL = os.path.join("HomeDomain", "Library", "FrontBoard", "applicationState.db")


def _safe_load_double_bplist(blob):
    import plistlib
    if not isinstance(blob, (bytes, bytearray)):
        return None
    try:
        parsed = plistlib.loads(bytes(blob))
    except Exception:
        return None
    if isinstance(parsed, (bytes, bytearray)) and parsed.startswith(b"bplist"):
        try:
            parsed = plistlib.loads(bytes(parsed))
        except Exception:
            return None
    return parsed


def _decode_compatibility_info(blob) -> tuple[Optional[str], Optional[str]]:
    parsed = _safe_load_double_bplist(blob)
    if not isinstance(parsed, dict):
        return None, None
    objects = parsed.get("$objects")
    if not isinstance(objects, list):
        return None, None

    def _at(idx: int) -> Optional[str]:
        if 0 <= idx < len(objects):
            v = objects[idx]
            if isinstance(v, str) and v and v != "$null":
                return v
        return None

    return _at(4), _at(3)


def _decode_snapshot_manifest(blob) -> list[str]:
    parsed = _safe_load_double_bplist(blob)
    if not isinstance(parsed, dict):
        return []
    objects = parsed.get("$objects")
    if not isinstance(objects, list):
        return []
    return [
        o for o in objects
        if isinstance(o, str) and o.startswith("sceneID:")
    ]


def _dir_size_bytes(folder: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(folder):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass
    return total


_EMPTY_APPS_RESPONSE = {
    "apps": [],
    "stats": {
        "total": 0,
        "user_apps": 0,
        "system_apps": 0,
        "by_category": {},
        "with_data_on_disk": 0,
        "total_sandbox_bytes": 0,
    },
}


@router.get("/evidence/{case_id}/installed-apps")
async def get_installed_apps(
    case_id: str,
    search: Optional[str] = None,
    category: Optional[str] = None,
):
    from app.services.database import list_acquisitions
    from app.services import app_catalog

    acqs = list_acquisitions(case_id)
    if not acqs:
        raise HTTPException(status_code=404, detail="No acquisitions for case")

    db_path: Optional[str] = None
    output_path: Optional[str] = None
    for acq in acqs:
        op = acq.get("output_path")
        if not op:
            continue
        candidate = os.path.join(op, _APPS_REL)
        if os.path.isfile(candidate):
            db_path = candidate
            output_path = op
            break

    if not db_path:
        return _EMPTY_APPS_RESPONSE

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        try:
            bid_rows = conn.execute(
                "SELECT application_identifier FROM application_identifier_tab"
            ).fetchall()
        except sqlite3.OperationalError as exc:
            logger.warning("applicationState.db schema mismatch: %s", exc)
            return _EMPTY_APPS_RESPONSE
        all_bundle_ids = sorted({
            r["application_identifier"]
            for r in bid_rows
            if r["application_identifier"]
        })

        try:
            kv_rows = conn.execute(
                """
                SELECT a.application_identifier AS bundle_id,
                       k.value AS blob,
                       kt.key AS key_name
                FROM kvs k
                JOIN application_identifier_tab a
                  ON k.application_identifier = a.id
                JOIN key_tab kt ON k.key = kt.id
                WHERE kt.key IN ('compatibilityInfo', 'XBApplicationSnapshotManifest')
                """
            ).fetchall()
        except sqlite3.OperationalError as exc:
            logger.warning("kvs schema mismatch: %s", exc)
            kv_rows = []
    finally:
        conn.close()

    per_bundle: dict[str, dict] = {}
    for r in kv_rows:
        bid = r["bundle_id"]
        if not bid:
            continue
        agg = per_bundle.setdefault(bid, {})
        if r["key_name"] == "compatibilityInfo":
            sp, bp = _decode_compatibility_info(r["blob"])
            if sp:
                agg.setdefault("sandbox_path", sp)
            if bp:
                agg.setdefault("bundle_path", bp)
        elif r["key_name"] == "XBApplicationSnapshotManifest":
            scenes = _decode_snapshot_manifest(r["blob"])
            if scenes:
                agg.setdefault("scenes", scenes)

    all_apps: list[dict] = []
    for bid in all_bundle_ids:
        info = per_bundle.get(bid, {})
        cat_info = app_catalog.lookup(bid)

        sandbox_size: Optional[int] = None
        if output_path:
            for prefix in ("AppDomain-", "AppDomainGroup-"):
                folder = os.path.join(output_path, f"{prefix}{bid}")
                if os.path.isdir(folder):
                    sandbox_size = _dir_size_bytes(folder)
                    break

        if cat_info["vendor"] == "Apple" or not cat_info["is_known"]:
            user_or_system = "system"
        elif cat_info["category"] != "System":
            user_or_system = "user"
        else:
            user_or_system = "system"

        scenes = info.get("scenes") or []
        all_apps.append({
            "bundle_id": bid,
            "display_name": cat_info["display_name"],
            "category": cat_info["category"],
            "vendor": cat_info["vendor"],
            "is_known": cat_info["is_known"],
            "sandbox_path": info.get("sandbox_path"),
            "bundle_path": info.get("bundle_path"),
            "sandbox_size": sandbox_size,
            "has_data": bool(sandbox_size and sandbox_size > 0),
            "last_scene_id": scenes[-1] if scenes else None,
            "scene_count": len(scenes),
            "user_or_system": user_or_system,
        })

    user_count = sum(1 for a in all_apps if a["user_or_system"] == "user")
    system_count = sum(1 for a in all_apps if a["user_or_system"] == "system")
    by_category: dict[str, int] = {}
    for a in all_apps:
        c = a["category"] or "Unknown"
        by_category[c] = by_category.get(c, 0) + 1
    with_data_count = sum(1 for a in all_apps if a["has_data"])
    total_bytes = sum(a["sandbox_size"] or 0 for a in all_apps)

    apps = list(all_apps)
    if search:
        s = search.strip().lower()
        apps = [
            a for a in apps
            if s in a["bundle_id"].lower()
            or s in (a["display_name"] or "").lower()
        ]
    if category and category != "all":
        if category in ("user", "system"):
            apps = [a for a in apps if a["user_or_system"] == category]
        else:
            apps = [a for a in apps if a["category"] == category]

    apps.sort(key=lambda a: (
        0 if a["user_or_system"] == "user" else 1,
        0 if a["is_known"] else 1,
        (a["display_name"] or "").lower(),
        a["bundle_id"].lower(),
    ))

    return {
        "apps": apps,
        "stats": {
            "total": len(all_apps),
            "user_apps": user_count,
            "system_apps": system_count,
            "by_category": by_category,
            "with_data_on_disk": with_data_count,
            "total_sandbox_bytes": total_bytes,
        },
    }


_PROTECTION_CLASS_NAMES = {
    6: "kSecAttrAccessibleWhenUnlocked",
    7: "kSecAttrAccessibleAfterFirstUnlock",
    8: "kSecAttrAccessibleAlways",
    9: "kSecAttrAccessibleWhenUnlockedThisDeviceOnly",
    10: "kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly",
    11: "kSecAttrAccessibleAlwaysThisDeviceOnly",
}


@router.get("/evidence/{case_id}/keychain")
async def get_keychain(
    case_id: str,
    table: Optional[str] = None,
    protection_class: Optional[int] = Query(None, alias="class"),
    cursor: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=10000),
):
    conn = _get_artifacts_conn(case_id)
    if not conn:
        raise HTTPException(status_code=404, detail="No parsed artifacts")

    try:
        try:
            meta_row = conn.execute(
                "SELECT * FROM keychain_meta ORDER BY parsed_at DESC LIMIT 1"
            ).fetchone()
        except sqlite3.OperationalError:
            return {
                "meta": {},
                "stats": {
                    "by_table": {"genp": 0, "inet": 0, "cert": 0, "keys": 0},
                    "by_class": {},
                    "this_device_only_count": 0,
                    "migratable_count": 0,
                },
                "items": [],
            }

        meta = dict(meta_row) if meta_row else {}

        try:
            by_table_rows = conn.execute(
                "SELECT table_name, COUNT(*) AS n FROM keychain_items GROUP BY table_name"
            ).fetchall()
            by_class_rows = conn.execute(
                "SELECT protection_class, COUNT(*) AS n FROM keychain_items "
                "GROUP BY protection_class"
            ).fetchall()
            tdo_row = conn.execute(
                "SELECT COUNT(*) AS n FROM keychain_items WHERE is_this_device_only = 1"
            ).fetchone()
            mig_row = conn.execute(
                "SELECT COUNT(*) AS n FROM keychain_items WHERE is_this_device_only = 0"
            ).fetchone()
        except sqlite3.OperationalError:
            return {
                "meta": meta,
                "stats": {
                    "by_table": {"genp": 0, "inet": 0, "cert": 0, "keys": 0},
                    "by_class": {},
                    "this_device_only_count": 0,
                    "migratable_count": 0,
                },
                "items": [],
            }

        by_table: dict[str, int] = {"genp": 0, "inet": 0, "cert": 0, "keys": 0}
        for r in by_table_rows:
            by_table[r["table_name"]] = int(r["n"])

        by_class: dict[str, int] = {}
        for r in by_class_rows:
            cls = r["protection_class"]
            if cls is None:
                continue
            by_class[str(int(cls))] = int(r["n"])

        where: list[str] = []
        params: list = []
        if table and table in ("genp", "inet", "cert", "keys"):
            where.append("table_name = ?")
            params.append(table)
        if protection_class is not None:
            where.append("protection_class = ?")
            params.append(protection_class)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        item_rows = conn.execute(
            f"""
            SELECT id, table_name, item_uuid, protection_class,
                   protection_class_name, is_this_device_only,
                   v_data_size, wrapped_key_hex, decrypted,
                   service, account, agrp, value
            FROM keychain_items
            {where_sql}
            ORDER BY id
            LIMIT ? OFFSET ?
            """,
            (*params, limit, cursor),
        ).fetchall()
    finally:
        conn.close()

    items = [
        {
            "id": r["id"],
            "table_name": r["table_name"],
            "item_uuid": r["item_uuid"],
            "protection_class": r["protection_class"],
            "protection_class_name": r["protection_class_name"]
                or _PROTECTION_CLASS_NAMES.get(r["protection_class"] or -1, "unknown"),
            "is_this_device_only": bool(r["is_this_device_only"]),
            "v_data_size": r["v_data_size"],
            "wrapped_key_hex": r["wrapped_key_hex"],
            "decrypted": bool(r["decrypted"]),
            "service": r["service"],
            "account": r["account"],
            "agrp": r["agrp"],
            "value": r["value"],
        }
        for r in item_rows
    ]

    return {
        "meta": meta,
        "stats": {
            "by_table": by_table,
            "by_class": by_class,
            "this_device_only_count": int(tdo_row["n"]) if tdo_row else 0,
            "migratable_count": int(mig_row["n"]) if mig_row else 0,
        },
        "items": items,
    }


_EMPTY_AI_RESPONSE = {
    "conversations": [],
    "stats": {
        "total_conversations": 0,
        "total_messages": 0,
        "total_chars": 0,
        "by_model": {},
        "archived_count": 0,
        "temporary_count": 0,
        "date_range": {"earliest": None, "latest": None},
        "account_uuid": None,
    },
}


@router.get("/evidence/{case_id}/ai-conversations")
async def get_ai_conversations(
    case_id: str,
    search: Optional[str] = None,
    model: Optional[str] = None,
    archived: Optional[int] = None,
):
    conn = _get_artifacts_conn(case_id)
    if not conn:
        raise HTTPException(status_code=404, detail="No parsed artifacts")
    try:
        try:
            rows = conn.execute(
                """
                SELECT conversation_uuid, title, message_count, total_chars,
                       creation_date, modification_date, default_model,
                       is_archived, is_do_not_remember, is_temporary_chat,
                       is_study_mode, account_uuid, file_size, app
                FROM ai_conversations
                ORDER BY modification_date DESC
                """
            ).fetchall()
        except sqlite3.OperationalError:
            return _EMPTY_AI_RESPONSE
    finally:
        conn.close()

    all_convs = [dict(r) for r in rows]

    by_model: dict[str, int] = {}
    for c in all_convs:
        m = c.get("default_model") or "(unknown)"
        by_model[m] = by_model.get(m, 0) + 1
    archived_count = sum(1 for c in all_convs if c.get("is_archived"))
    temporary_count = sum(1 for c in all_convs if c.get("is_temporary_chat"))
    accounts = {c.get("account_uuid") for c in all_convs if c.get("account_uuid")}
    account_uuid = next(iter(accounts), None) if len(accounts) == 1 else None

    earliest = None
    latest = None
    for c in all_convs:
        for fld in ("creation_date", "modification_date"):
            v = c.get(fld)
            if not v:
                continue
            if earliest is None or v < earliest:
                earliest = v
            if latest is None or v > latest:
                latest = v

    total_messages = sum(int(c.get("message_count") or 0) for c in all_convs)
    total_chars = sum(int(c.get("total_chars") or 0) for c in all_convs)

    convs = list(all_convs)
    if search:
        s = search.strip().lower()
        convs = [c for c in convs if s in (c.get("title") or "").lower()]
    if model:
        convs = [c for c in convs if (c.get("default_model") or "") == model]
    if archived is not None:
        convs = [c for c in convs if bool(c.get("is_archived")) == bool(archived)]

    for c in convs:
        for k in ("is_archived", "is_do_not_remember", "is_temporary_chat",
                  "is_study_mode"):
            c[k] = bool(c.get(k))

    return {
        "conversations": convs,
        "stats": {
            "total_conversations": len(all_convs),
            "total_messages": total_messages,
            "total_chars": total_chars,
            "by_model": by_model,
            "archived_count": archived_count,
            "temporary_count": temporary_count,
            "date_range": {"earliest": earliest, "latest": latest},
            "account_uuid": account_uuid,
        },
    }


@router.get("/evidence/{case_id}/ai-conversations/{conversation_uuid}")
async def get_ai_conversation_detail(case_id: str, conversation_uuid: str):
    conn = _get_artifacts_conn(case_id)
    if not conn:
        raise HTTPException(status_code=404, detail="No parsed artifacts")
    try:
        try:
            meta_row = conn.execute(
                """
                SELECT * FROM ai_conversations
                WHERE conversation_uuid = ?
                LIMIT 1
                """,
                (conversation_uuid,),
            ).fetchone()
        except sqlite3.OperationalError:
            raise HTTPException(status_code=404, detail="No ai_conversations table")
        if not meta_row:
            raise HTTPException(status_code=404, detail="Conversation not found")
        meta = dict(meta_row)

        try:
            msg_rows = conn.execute(
                """
                SELECT seq, role, model_slug, create_time, content_text,
                       content_type, image_assets_json, code_language,
                       tool_name, raw_node_json
                FROM ai_messages
                WHERE conversation_uuid = ?
                ORDER BY seq ASC
                """,
                (conversation_uuid,),
            ).fetchall()
        except sqlite3.OperationalError:
            msg_rows = conn.execute(
                """
                SELECT seq, role, model_slug, create_time, content_text
                FROM ai_messages
                WHERE conversation_uuid = ?
                ORDER BY seq ASC
                """,
                (conversation_uuid,),
            ).fetchall()
    finally:
        conn.close()

    for k in ("is_archived", "is_do_not_remember", "is_temporary_chat",
              "is_study_mode"):
        meta[k] = bool(meta.get(k))

    messages: list[dict] = []
    for r in msg_rows:
        m = dict(r)
        ia_raw = m.pop("image_assets_json", None)
        try:
            m["image_assets"] = json.loads(ia_raw) if ia_raw else []
        except (TypeError, ValueError):
            m["image_assets"] = []
        rn_raw = m.pop("raw_node_json", None)
        try:
            m["raw_node"] = json.loads(rn_raw) if rn_raw else None
        except (TypeError, ValueError):
            m["raw_node"] = None
        if not m.get("content_type"):
            m["content_type"] = "text"
        messages.append(m)

    return {
        "meta": meta,
        "custom_instructions": {
            "user": meta.get("custom_instructions_user") or "",
            "model": meta.get("custom_instructions_model") or "",
        },
        "messages": messages,
    }


@router.get("/evidence/{case_id}/web-history")
async def get_web_history(case_id: str, search: Optional[str] = None):
    conn = _get_artifacts_conn(case_id)
    if not conn:
        raise HTTPException(status_code=404, detail="No parsed artifacts")

    try:
        if search:
            rows = conn.execute(
                "SELECT * FROM web_history WHERE url LIKE ? OR title LIKE ? ORDER BY timestamp_unix DESC",
                (f"%{search}%", f"%{search}%"),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM web_history ORDER BY timestamp_unix DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _resolve_photo(case_id: str, photo_id: int) -> Optional[dict]:
    conn = _get_artifacts_conn(case_id)
    if not conn:
        return None
    try:
        row = conn.execute(
            """
            SELECT te.id, te.timestamp, te.timestamp_unix, te.acquisition_id,
                   l.label AS filename, l.metadata,
                   l.latitude, l.longitude
            FROM timeline_events te
            JOIN locations l ON te.source_id = l.id
            WHERE te.id = ?
              AND te.event_type = 'photo'
              AND te.source_table = 'locations'
            LIMIT 1
            """,
            (photo_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        meta = json.loads(row["metadata"] or "{}") or {}
    except Exception:
        meta = {}
    rel_path = meta.get("file") or ""
    if not rel_path:
        return None
    acq = get_acquisition(row["acquisition_id"])
    if not acq or not acq.get("output_path"):
        return None
    out_real = os.path.realpath(acq["output_path"])
    full_path = os.path.realpath(os.path.join(out_real, rel_path))
    if full_path != out_real and not full_path.startswith(out_real + os.sep):
        return None
    if not os.path.isfile(full_path):
        return None
    try:
        size = os.path.getsize(full_path)
    except OSError:
        size = 0
    return {
        "id": row["id"],
        "full_path": full_path,
        "filename": row["filename"] or os.path.basename(full_path),
        "timestamp": row["timestamp"],
        "size_bytes": size,
        "gps_lat": row["latitude"],
        "gps_lon": row["longitude"],
        "acquisition_id": row["acquisition_id"],
    }


@router.get("/evidence/{case_id}/photos")
async def get_photos(
    case_id: str,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    with_gps: Optional[bool] = None,
):
    conn = _get_artifacts_conn(case_id)
    if not conn:
        raise HTTPException(status_code=404, detail="No parsed artifacts")
    try:
        where = ["te.event_type = 'photo'", "te.source_table = 'locations'"]
        if with_gps is True:
            where.append("l.latitude IS NOT NULL AND l.longitude IS NOT NULL")
        elif with_gps is False:
            where.append("(l.latitude IS NULL OR l.longitude IS NULL)")
        where_clause = " AND ".join(where)

        total = conn.execute(
            f"""SELECT COUNT(*) AS c FROM timeline_events te
                JOIN locations l ON te.source_id = l.id
                WHERE {where_clause}"""
        ).fetchone()["c"]

        rows = conn.execute(
            f"""SELECT te.id, te.timestamp, te.timestamp_unix,
                       l.label AS filename, l.metadata,
                       l.latitude, l.longitude
                FROM timeline_events te
                JOIN locations l ON te.source_id = l.id
                WHERE {where_clause}
                ORDER BY te.timestamp_unix DESC
                LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()

        photos = []
        for r in rows:
            try:
                meta = json.loads(r["metadata"] or "{}") or {}
            except Exception:
                meta = {}
            photos.append({
                "id": r["id"],
                "filename": r["filename"] or "",
                "path": meta.get("file", ""),
                "thumbnail_url": f"/analysis/evidence/{case_id}/photos/{r['id']}/thumb",
                "preview_url":   f"/analysis/evidence/{case_id}/photos/{r['id']}/preview",
                "timestamp": r["timestamp"],
                "size_bytes": None,
                "gps_lat": r["latitude"],
                "gps_lon": r["longitude"],
                "camera_make": None,
                "camera_model": None,
                "source_app": None,
            })
        return {
            "photos": photos,
            "total": int(total or 0),
            "limit": limit,
            "offset": offset,
        }
    finally:
        conn.close()


def _thumb_cache_dir(case_id: str) -> Path:
    p = Path(tempfile.gettempdir()) / "pixtra-thumbs" / case_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _serve_resized(case_id: str, photo_id: int, *, long_edge: int, suffix: str):
    if Image is None:
        raise HTTPException(
            status_code=500,
            detail="Pillow is not installed (pip install Pillow pillow-heif)",
        )
    photo = _resolve_photo(case_id, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    cache_path = _thumb_cache_dir(case_id) / f"{photo_id}_{suffix}.jpg"
    if not cache_path.exists():
        try:
            with Image.open(photo["full_path"]) as im:
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                im.thumbnail((long_edge, long_edge))
                im.save(cache_path, format="JPEG", quality=82)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Could not decode {photo['filename']}: {exc}",
            )
    return FileResponse(
        cache_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/evidence/{case_id}/photos/{photo_id}/thumb")
async def get_photo_thumb(case_id: str, photo_id: int):
    return _serve_resized(case_id, photo_id, long_edge=200, suffix="thumb")


@router.get("/evidence/{case_id}/photos/{photo_id}/preview")
async def get_photo_preview(case_id: str, photo_id: int):
    return _serve_resized(case_id, photo_id, long_edge=1200, suffix="preview")


@router.get("/graph/{case_id}")
async def get_graph(case_id: str):
    case_dir = case_dir_for(case_id)
    graph = get_entity_graph(case_dir)
    graph["case_id"] = case_id
    return graph


@router.get("/timeline/{case_id}")
async def get_timeline(
    case_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = Query(default=200, le=1000),
    offset: int = 0,
):
    conn = _get_artifacts_conn(case_id)
    if not conn:
        return {"case_id": case_id, "events": [], "density": []}

    try:
        query = "SELECT * FROM timeline_events WHERE 1=1"
        params = []

        if start:
            query += " AND timestamp >= ?"
            params.append(start)
        if end:
            query += " AND timestamp <= ?"
            params.append(end)
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)

        query += " ORDER BY timestamp_unix DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        events = [dict(r) for r in conn.execute(query, params).fetchall()]

        density = []
        try:
            density_rows = conn.execute("""
                SELECT DATE(timestamp) as day, COUNT(*) as event_count
                FROM timeline_events
                GROUP BY day ORDER BY day ASC
            """).fetchall()
            density = [{"date": r["day"], "count": r["event_count"]} for r in density_rows]
        except Exception:
            pass

        total = conn.execute("SELECT COUNT(*) FROM timeline_events").fetchone()[0]

        return {
            "case_id": case_id,
            "events": events,
            "density": density,
            "total_events": total,
        }
    finally:
        conn.close()


NOTES_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS examiner_notes (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        content TEXT,
        include_in_report INTEGER DEFAULT 0,
        entity_refs TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        examiner TEXT
    )
"""


@router.get("/notes/{case_id}")
async def list_notes(case_id: str):
    conn = _get_artifacts_conn(case_id)
    if not conn:
        return {"case_id": case_id, "notes": []}

    try:
        conn.execute(NOTES_TABLE_SQL)
        conn.commit()
        rows = conn.execute("SELECT * FROM examiner_notes ORDER BY updated_at DESC").fetchall()
        return {"case_id": case_id, "notes": [dict(r) for r in rows]}
    finally:
        conn.close()


class NoteCreate(BaseModel):
    title: str
    content: str = ""
    examiner: str = ""


@router.post("/notes/{case_id}")
async def create_note(case_id: str, data: NoteCreate):
    case_dir = case_dir_for(case_id)
    os.makedirs(case_dir, exist_ok=True)

    db_path = os.path.join(case_dir, "artifacts.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        conn.execute(NOTES_TABLE_SQL)
        note_id = uuid4().hex[:12]
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO examiner_notes (id, title, content, created_at, updated_at, examiner) VALUES (?, ?, ?, ?, ?, ?)",
            (note_id, data.title, data.content, now, now, data.examiner),
        )
        conn.commit()
        return {"id": note_id, "title": data.title, "created_at": now}
    finally:
        conn.close()


_FILE_EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".gif", ".heic", ".heif", ".webp", ".bmp", ".tiff"},
    "video": {".mp4", ".mov", ".avi", ".mkv", ".3gp", ".m4v"},
    "audio": {".mp3", ".m4a", ".aac", ".wav", ".opus", ".caf", ".amr"},
    "document": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".csv", ".pages", ".numbers"},
}

_FILES_CACHE_TTL_SEC = 300
_files_cache: "dict[tuple[str, str, Optional[str]], tuple[float, list]]" = {}


def _walk_extraction_files(
    case_id: str, path: str, file_type: Optional[str]
) -> "tuple[list, Optional[str]]":
    from app.services.database import list_acquisitions

    acqs = list_acquisitions(case_id)
    if not acqs:
        return [], "No acquisitions found"

    files: list = []
    for acq in acqs:
        output_path = acq.get("output_path")
        if not output_path or not os.path.isdir(output_path):
            continue

        scan_dir = os.path.join(output_path, path) if path else output_path
        if not os.path.isdir(scan_dir):
            continue

        for root, _dirs, filenames in os.walk(scan_dir):
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()

                if file_type and ext not in _FILE_EXTENSIONS.get(file_type, set()):
                    continue

                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, output_path)

                detected_type = "other"
                for ft, exts in _FILE_EXTENSIONS.items():
                    if ext in exts:
                        detected_type = ft
                        break

                try:
                    size = os.path.getsize(fpath)
                except OSError:
                    size = 0

                files.append({
                    "name": fname,
                    "path": rel_path,
                    "type": detected_type,
                    "size_bytes": size,
                    "acquisition_id": acq["id"],
                })

            if len(files) > 2000:
                break
        if len(files) > 2000:
            break

    return files, None


def _get_cached_or_walk(
    case_id: str, path: str, file_type: Optional[str]
) -> "tuple[list, Optional[str]]":
    key = (case_id, path, file_type)
    now = time.time()
    cached = _files_cache.get(key)
    if cached and now - cached[0] < _FILES_CACHE_TTL_SEC:
        return cached[1], None
    files, message = _walk_extraction_files(case_id, path, file_type)
    if message is None:
        _files_cache[key] = (now, files)
    return files, message


@router.get("/files/{case_id}")
async def list_extraction_files(
    case_id: str,
    path: str = "",
    file_type: Optional[str] = None,
):
    files, message = _get_cached_or_walk(case_id, path, file_type)
    if message is not None:
        return {"files": files, "message": message}
    return {"files": files, "total": len(files)}


@router.get("/media/{case_id}/{acquisition_id}/{file_path:path}")
async def serve_media_file(case_id: str, acquisition_id: str, file_path: str):
    from fastapi.responses import FileResponse
    from app.services.database import get_acquisition

    acq = get_acquisition(acquisition_id)
    if not acq:
        raise HTTPException(status_code=404, detail="Acquisition not found")
    if acq["case_id"] != case_id:
        raise HTTPException(status_code=403, detail="Acquisition does not belong to this case")

    output_path = acq.get("output_path")
    if not output_path:
        raise HTTPException(status_code=404, detail="No output path")

    full_path = os.path.join(output_path, file_path)

    real_output = os.path.realpath(output_path)
    real_file = os.path.realpath(full_path)
    if real_file != real_output and not real_file.startswith(real_output + os.sep):
        raise HTTPException(status_code=403, detail="Path traversal blocked")

    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(full_path)

import json
import logging
import os
import sqlite3
import struct
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("pixtra.parser")

APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)

UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class ArtifactsDB:

    def __init__(self, case_dir: str):
        self.db_path = os.path.join(case_dir, "artifacts.db")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,          -- 'whatsapp', 'imessage', 'sms', 'telegram', etc.
                chat_id TEXT,                  -- conversation/group identifier
                chat_name TEXT,
                sender TEXT,
                sender_name TEXT,
                recipient TEXT,
                text TEXT,
                timestamp TEXT,
                timestamp_unix REAL,
                is_from_me INTEGER DEFAULT 0,
                is_read INTEGER DEFAULT 1,
                is_deleted INTEGER DEFAULT 0,
                is_recovered INTEGER DEFAULT 0,
                has_attachment INTEGER DEFAULT 0,
                attachment_path TEXT,
                attachment_type TEXT,           -- 'image', 'video', 'audio', 'document'
                metadata TEXT,                 -- JSON blob for extra fields
                device_id TEXT,
                acquisition_id TEXT
            );

            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                name TEXT,
                phone TEXT,
                email TEXT,
                organization TEXT,
                photo_path TEXT,
                notes TEXT,
                metadata TEXT,
                device_id TEXT,
                acquisition_id TEXT
            );

            CREATE TABLE IF NOT EXISTS calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                number TEXT,
                name TEXT,
                direction TEXT,                -- 'incoming', 'outgoing', 'missed'
                duration_seconds INTEGER,
                timestamp TEXT,
                timestamp_unix REAL,
                is_deleted INTEGER DEFAULT 0,
                metadata TEXT,
                device_id TEXT,
                acquisition_id TEXT
            );

            CREATE TABLE IF NOT EXISTS locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,           -- 'gps', 'wifi', 'cell_tower', 'exif', 'app'
                latitude REAL,
                longitude REAL,
                altitude REAL,
                accuracy REAL,
                timestamp TEXT,
                timestamp_unix REAL,
                label TEXT,                    -- place name if known
                metadata TEXT,
                device_id TEXT,
                acquisition_id TEXT
            );

            CREATE TABLE IF NOT EXISTS web_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,           -- 'safari', 'chrome'
                url TEXT,
                title TEXT,
                visit_count INTEGER DEFAULT 1,
                timestamp TEXT,
                timestamp_unix REAL,
                search_term TEXT,              -- extracted search query if applicable
                metadata TEXT,
                device_id TEXT,
                acquisition_id TEXT
            );

            CREATE TABLE IF NOT EXISTS wifi_networks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ssid TEXT,
                bssid TEXT,
                last_joined TEXT,
                last_joined_unix REAL,
                password TEXT,                 -- from keychain if available
                metadata TEXT,
                device_id TEXT,
                acquisition_id TEXT
            );

            CREATE TABLE IF NOT EXISTS installed_apps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bundle_id TEXT,                -- iOS bundle or Android package
                app_name TEXT,
                version TEXT,
                install_date TEXT,
                storage_bytes INTEGER,
                metadata TEXT,
                device_id TEXT,
                acquisition_id TEXT
            );

            CREATE TABLE IF NOT EXISTS keychain_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service TEXT,
                account TEXT,
                label TEXT,
                value TEXT,                    -- password/token (encrypted at rest)
                item_class TEXT,               -- 'password', 'key', 'certificate', 'identity'
                metadata TEXT,
                device_id TEXT,
                acquisition_id TEXT
            );

            CREATE TABLE IF NOT EXISTS timeline_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,       -- 'message', 'call', 'photo', 'location', etc.
                timestamp TEXT NOT NULL,
                timestamp_unix REAL NOT NULL,
                title TEXT,
                description TEXT,
                source_table TEXT,              -- which artifacts table
                source_id INTEGER,              -- row ID in source table
                is_deleted INTEGER DEFAULT 0,
                device_id TEXT,
                acquisition_id TEXT
            );

            -- Entity graph tables
            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,      -- 'person', 'location', 'device', 'file', 'app'
                name TEXT NOT NULL,
                identifier TEXT,               -- phone number, email, coordinates, etc.
                occurrence_count INTEGER DEFAULT 1,
                first_seen TEXT,
                last_seen TEXT,
                metadata TEXT,
                device_id TEXT
            );

            CREATE TABLE IF NOT EXISTS entity_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_entity_id INTEGER REFERENCES entities(id),
                target_entity_id INTEGER REFERENCES entities(id),
                relationship TEXT,             -- 'messaged', 'called', 'co_located', 'mentioned', etc.
                weight REAL DEFAULT 1.0,
                first_occurrence TEXT,
                last_occurrence TEXT,
                metadata TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id);
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp_unix);
            CREATE INDEX IF NOT EXISTS idx_messages_source ON messages(source);
            CREATE INDEX IF NOT EXISTS idx_calls_timestamp ON calls(timestamp_unix);
            CREATE INDEX IF NOT EXISTS idx_locations_timestamp ON locations(timestamp_unix);
            CREATE INDEX IF NOT EXISTS idx_timeline_timestamp ON timeline_events(timestamp_unix);
            CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
            CREATE INDEX IF NOT EXISTS idx_edges_source ON entity_edges(source_entity_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON entity_edges(target_entity_id);
        """)
        self.conn.commit()

    def insert_message(self, msg: dict):
        cols = [k for k in msg if k != "id"]
        placeholders = ", ".join(f":{k}" for k in cols)
        col_names = ", ".join(cols)
        self.conn.execute(
            f"INSERT INTO messages ({col_names}) VALUES ({placeholders})", msg
        )

    def insert_contact(self, contact: dict):
        cols = [k for k in contact if k != "id"]
        placeholders = ", ".join(f":{k}" for k in cols)
        col_names = ", ".join(cols)
        self.conn.execute(
            f"INSERT INTO contacts ({col_names}) VALUES ({placeholders})", contact
        )

    def insert_call(self, call: dict):
        cols = [k for k in call if k != "id"]
        placeholders = ", ".join(f":{k}" for k in cols)
        col_names = ", ".join(cols)
        self.conn.execute(
            f"INSERT INTO calls ({col_names}) VALUES ({placeholders})", call
        )

    def insert_location(self, loc: dict):
        cols = [k for k in loc if k != "id"]
        placeholders = ", ".join(f":{k}" for k in cols)
        col_names = ", ".join(cols)
        self.conn.execute(
            f"INSERT INTO locations ({col_names}) VALUES ({placeholders})", loc
        )

    def insert_web_history(self, entry: dict):
        cols = [k for k in entry if k != "id"]
        placeholders = ", ".join(f":{k}" for k in cols)
        col_names = ", ".join(cols)
        self.conn.execute(
            f"INSERT INTO web_history ({col_names}) VALUES ({placeholders})", entry
        )

    def insert_timeline_event(self, event: dict):
        cols = [k for k in event if k != "id"]
        placeholders = ", ".join(f":{k}" for k in cols)
        col_names = ", ".join(cols)
        self.conn.execute(
            f"INSERT INTO timeline_events ({col_names}) VALUES ({placeholders})", event
        )

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


def apple_timestamp_to_iso(ts: float) -> tuple[str, float]:
    if ts is None or ts == 0:
        return None, 0
    dt = APPLE_EPOCH + timedelta(seconds=ts)
    return dt.isoformat(), dt.timestamp()


def unix_timestamp_to_iso(ts: float) -> tuple[str, float]:
    if ts is None or ts == 0:
        return None, 0
    if ts > 1e12:
        ts = ts / 1000.0
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.isoformat(), ts


class IMESSAGEParser:

    def parse(self, db_path: str, artifacts: ArtifactsDB, device_id: str, acquisition_id: str):
        if not os.path.exists(db_path):
            logger.warning(f"sms.db not found at {db_path}")
            return 0

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        count = 0

        try:
            rows = conn.execute("""
                SELECT
                    m.ROWID,
                    m.text,
                    m.date as timestamp,
                    m.is_from_me,
                    m.is_read,
                    m.cache_has_attachments,
                    m.date_delivered,
                    m.date_read,
                    h.id as handle_id,
                    h.uncanonicalized_id as phone,
                    h.service as service,
                    c.display_name as chat_name,
                    c.chat_identifier as chat_id
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                LEFT JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
                LEFT JOIN chat c ON cmj.chat_id = c.ROWID
                ORDER BY m.date ASC
            """).fetchall()

            for row in rows:
                ts_iso, ts_unix = apple_timestamp_to_iso(
                    row["timestamp"] / 1e9 if row["timestamp"] and row["timestamp"] > 1e15 else row["timestamp"]
                )

                msg = {
                    "source": "imessage" if row["service"] == "iMessage" else "sms",
                    "chat_id": row["chat_id"] or row["phone"],
                    "chat_name": row["chat_name"] or row["phone"],
                    "sender": None if row["is_from_me"] else row["phone"],
                    "sender_name": None,
                    "recipient": row["phone"] if row["is_from_me"] else None,
                    "text": row["text"],
                    "timestamp": ts_iso,
                    "timestamp_unix": ts_unix,
                    "is_from_me": row["is_from_me"],
                    "is_read": row["is_read"],
                    "has_attachment": row["cache_has_attachments"] or 0,
                    "device_id": device_id,
                    "acquisition_id": acquisition_id,
                }
                artifacts.insert_message(msg)

                if ts_iso:
                    artifacts.insert_timeline_event({
                        "event_type": "message",
                        "timestamp": ts_iso,
                        "timestamp_unix": ts_unix,
                        "title": f"{'Sent' if row['is_from_me'] else 'Received'} message",
                        "description": (row["text"] or "")[:200],
                        "source_table": "messages",
                        "source_id": row["ROWID"],
                        "device_id": device_id,
                        "acquisition_id": acquisition_id,
                    })
                count += 1

            artifacts.commit()
            logger.info(f"Parsed {count} iMessage/SMS messages from {db_path}")

        except Exception as e:
            logger.error(f"iMessage parsing failed: {e}")
        finally:
            conn.close()

        return count


class WhatsAppParser:

    def parse_ios(self, db_path: str, artifacts: ArtifactsDB, device_id: str, acquisition_id: str):
        if not os.path.exists(db_path):
            logger.warning(f"WhatsApp DB not found at {db_path}")
            return 0

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        count = 0

        try:
            rows = conn.execute("""
                SELECT
                    m.Z_PK,
                    m.ZTEXT,
                    m.ZMESSAGEDATE,
                    m.ZISFROMME,
                    m.ZMESSAGETYPE,
                    m.ZSTARRED,
                    cs.ZCONTACTJID as chat_jid,
                    cs.ZPARTNERNAME as chat_name,
                    cs.ZGROUPINFO as is_group
                FROM ZWAMESSAGE m
                LEFT JOIN ZWACHATSESSION cs ON m.ZCHATSESSION = cs.Z_PK
                ORDER BY m.ZMESSAGEDATE ASC
            """).fetchall()

            for row in rows:
                ts_iso, ts_unix = apple_timestamp_to_iso(row["ZMESSAGEDATE"])
                jid = row["chat_jid"] or ""
                sender_phone = jid.split("@")[0] if "@" in jid else jid

                msg = {
                    "source": "whatsapp",
                    "chat_id": jid,
                    "chat_name": row["chat_name"] or sender_phone,
                    "sender": None if row["ZISFROMME"] else sender_phone,
                    "sender_name": row["chat_name"] if not row["ZISFROMME"] else None,
                    "text": row["ZTEXT"],
                    "timestamp": ts_iso,
                    "timestamp_unix": ts_unix,
                    "is_from_me": row["ZISFROMME"] or 0,
                    "metadata": json.dumps({
                        "message_type": row["ZMESSAGETYPE"],
                        "starred": row["ZSTARRED"],
                        "is_group": bool(row["is_group"]),
                    }),
                    "device_id": device_id,
                    "acquisition_id": acquisition_id,
                }
                artifacts.insert_message(msg)

                if ts_iso:
                    artifacts.insert_timeline_event({
                        "event_type": "message",
                        "timestamp": ts_iso,
                        "timestamp_unix": ts_unix,
                        "title": f"WhatsApp: {'Sent' if row['ZISFROMME'] else 'Received'}",
                        "description": (row["ZTEXT"] or "")[:200],
                        "source_table": "messages",
                        "source_id": row["Z_PK"],
                        "device_id": device_id,
                        "acquisition_id": acquisition_id,
                    })
                count += 1

            artifacts.commit()
            logger.info(f"Parsed {count} WhatsApp messages (iOS) from {db_path}")

        except Exception as e:
            logger.error(f"WhatsApp iOS parsing failed: {e}")
        finally:
            conn.close()
        return count

    def parse_android(self, db_path: str, artifacts: ArtifactsDB, device_id: str, acquisition_id: str):
        if not os.path.exists(db_path):
            logger.warning(f"WhatsApp msgstore.db not found at {db_path}")
            return 0

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        count = 0

        try:
            rows = conn.execute("""
                SELECT
                    m._id,
                    m.data as text,
                    m.timestamp,
                    m.key_from_me,
                    m.key_remote_jid,
                    m.remote_resource,
                    m.media_wa_type,
                    m.media_size,
                    j.subject as group_name
                FROM messages m
                LEFT JOIN jid j ON m.key_remote_jid = j.raw_string
                ORDER BY m.timestamp ASC
            """).fetchall()

            for row in rows:
                ts_iso, ts_unix = unix_timestamp_to_iso(row["timestamp"])
                jid = row["key_remote_jid"] or ""
                sender_phone = jid.split("@")[0] if "@" in jid else jid

                msg = {
                    "source": "whatsapp",
                    "chat_id": jid,
                    "chat_name": row["group_name"] or sender_phone,
                    "sender": row["remote_resource"] if not row["key_from_me"] else None,
                    "text": row["text"],
                    "timestamp": ts_iso,
                    "timestamp_unix": ts_unix,
                    "is_from_me": row["key_from_me"] or 0,
                    "metadata": json.dumps({"media_type": row["media_wa_type"]}),
                    "device_id": device_id,
                    "acquisition_id": acquisition_id,
                }
                artifacts.insert_message(msg)
                count += 1

            artifacts.commit()
            logger.info(f"Parsed {count} WhatsApp messages (Android) from {db_path}")

        except Exception as e:
            logger.error(f"WhatsApp Android parsing failed: {e}")
        finally:
            conn.close()
        return count


class CallLogParser:

    def parse_ios(self, db_path: str, artifacts: ArtifactsDB, device_id: str, acquisition_id: str):
        if not os.path.exists(db_path):
            return 0

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        count = 0

        try:
            rows = conn.execute("""
                SELECT
                    Z_PK,
                    ZADDRESS as number,
                    ZDURATION as duration,
                    ZDATE as timestamp,
                    ZORIGINATED as originated,
                    ZANSWERED as answered,
                    ZCALLTYPE as call_type
                FROM ZCALLRECORD
                ORDER BY ZDATE ASC
            """).fetchall()

            for row in rows:
                ts_iso, ts_unix = apple_timestamp_to_iso(row["timestamp"])

                if row["originated"]:
                    direction = "outgoing"
                elif row["answered"]:
                    direction = "incoming"
                else:
                    direction = "missed"

                call = {
                    "source": "ios_callhistory",
                    "number": row["number"],
                    "direction": direction,
                    "duration_seconds": int(row["duration"] or 0),
                    "timestamp": ts_iso,
                    "timestamp_unix": ts_unix,
                    "device_id": device_id,
                    "acquisition_id": acquisition_id,
                }
                artifacts.insert_call(call)

                if ts_iso:
                    artifacts.insert_timeline_event({
                        "event_type": "call",
                        "timestamp": ts_iso,
                        "timestamp_unix": ts_unix,
                        "title": f"{direction.capitalize()} call",
                        "description": f"{row['number']} - {int(row['duration'] or 0)}s",
                        "source_table": "calls",
                        "source_id": row["Z_PK"],
                        "device_id": device_id,
                        "acquisition_id": acquisition_id,
                    })
                count += 1

            artifacts.commit()
            logger.info(f"Parsed {count} call records from {db_path}")

        except Exception as e:
            logger.error(f"Call log parsing failed: {e}")
        finally:
            conn.close()
        return count


class SafariHistoryParser:

    def parse(self, db_path: str, artifacts: ArtifactsDB, device_id: str, acquisition_id: str):
        if not os.path.exists(db_path):
            return 0

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        count = 0

        try:
            rows = conn.execute("""
                SELECT
                    hv.id,
                    hi.url,
                    hv.title,
                    hv.visit_time,
                    hi.visit_count
                FROM history_visits hv
                JOIN history_items hi ON hv.history_item = hi.id
                ORDER BY hv.visit_time ASC
            """).fetchall()

            for row in rows:
                ts_iso, ts_unix = apple_timestamp_to_iso(row["visit_time"])

                url = row["url"] or ""
                search_term = None
                if "google.com/search" in url and "q=" in url:
                    search_term = url.split("q=")[1].split("&")[0].replace("+", " ")
                elif "bing.com/search" in url and "q=" in url:
                    search_term = url.split("q=")[1].split("&")[0].replace("+", " ")

                entry = {
                    "source": "safari",
                    "url": url,
                    "title": row["title"],
                    "visit_count": row["visit_count"],
                    "timestamp": ts_iso,
                    "timestamp_unix": ts_unix,
                    "search_term": search_term,
                    "device_id": device_id,
                    "acquisition_id": acquisition_id,
                }
                artifacts.insert_web_history(entry)
                count += 1

            artifacts.commit()
            logger.info(f"Parsed {count} Safari history entries from {db_path}")

        except Exception as e:
            logger.error(f"Safari history parsing failed: {e}")
        finally:
            conn.close()
        return count


class LocationParser:

    def parse_significant_locations(self, db_path: str, artifacts: ArtifactsDB,
                                     device_id: str, acquisition_id: str):
        if not os.path.exists(db_path):
            return 0

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        count = 0

        try:
            for table in ["ZRTLEARNEDLOCATIONOFINTERESTVISITMO", "ZRTLEARNEDVISITMO"]:
                try:
                    rows = conn.execute(f"""
                        SELECT
                            Z_PK,
                            ZLOCATIONLATITUDE as lat,
                            ZLOCATIONLONGITUDE as lon,
                            ZENTRYDATE as entry_time,
                            ZEXITDATE as exit_time
                        FROM {table}
                        WHERE ZLOCATIONLATITUDE IS NOT NULL
                        ORDER BY ZENTRYDATE ASC
                    """).fetchall()

                    for row in rows:
                        ts_iso, ts_unix = apple_timestamp_to_iso(row["entry_time"])
                        loc = {
                            "source": "significant_locations",
                            "latitude": row["lat"],
                            "longitude": row["lon"],
                            "timestamp": ts_iso,
                            "timestamp_unix": ts_unix,
                            "device_id": device_id,
                            "acquisition_id": acquisition_id,
                        }
                        artifacts.insert_location(loc)

                        if ts_iso:
                            artifacts.insert_timeline_event({
                                "event_type": "location",
                                "timestamp": ts_iso,
                                "timestamp_unix": ts_unix,
                                "title": "Location visit",
                                "description": f"{row['lat']:.5f}, {row['lon']:.5f}",
                                "source_table": "locations",
                                "source_id": row["Z_PK"],
                                "device_id": device_id,
                                "acquisition_id": acquisition_id,
                            })
                        count += 1
                    break
                except sqlite3.OperationalError:
                    continue

            artifacts.commit()
            logger.info(f"Parsed {count} significant locations from {db_path}")

        except Exception as e:
            logger.error(f"Location parsing failed: {e}")
        finally:
            conn.close()
        return count


class EXIFParser:

    GPS_IFD_TAG = 0x8825
    EXIF_IFD_TAG = 0x8769
    GPS_LATITUDE_REF = 0x0001
    GPS_LATITUDE = 0x0002
    GPS_LONGITUDE_REF = 0x0003
    GPS_LONGITUDE = 0x0004
    GPS_ALTITUDE = 0x0006
    GPS_TIMESTAMP = 0x0007
    GPS_DATESTAMP = 0x001D
    DATE_TIME_ORIGINAL = 0x9003

    def parse_directory(self, dir_path: str, artifacts: ArtifactsDB,
                        device_id: str, acquisition_id: str) -> int:
        count = 0
        image_exts = {".jpg", ".jpeg", ".heic", ".tiff", ".tif"}

        for root, dirs, files in os.walk(dir_path):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in image_exts:
                    continue

                fpath = os.path.join(root, fname)
                try:
                    exif = self._read_exif_jpeg(fpath)
                    if not exif:
                        continue

                    lat = exif.get("latitude")
                    lon = exif.get("longitude")
                    ts_iso = exif.get("datetime")
                    ts_unix = 0

                    if ts_iso:
                        try:
                            dt = datetime.strptime(ts_iso, "%Y:%m:%d %H:%M:%S")
                            dt = dt.replace(tzinfo=timezone.utc)
                            ts_iso = dt.isoformat()
                            ts_unix = dt.timestamp()
                        except (ValueError, TypeError):
                            ts_iso = None

                    if lat is not None and lon is not None:
                        loc = {
                            "source": "exif",
                            "latitude": lat,
                            "longitude": lon,
                            "timestamp": ts_iso,
                            "timestamp_unix": ts_unix,
                            "label": fname,
                            "metadata": json.dumps({
                                "file": os.path.relpath(fpath, dir_path),
                                "altitude": exif.get("altitude"),
                            }),
                            "device_id": device_id,
                            "acquisition_id": acquisition_id,
                        }
                        artifacts.insert_location(loc)

                        if ts_iso:
                            artifacts.insert_timeline_event({
                                "event_type": "photo",
                                "timestamp": ts_iso,
                                "timestamp_unix": ts_unix,
                                "title": f"Photo: {fname}",
                                "description": f"GPS: {lat:.5f}, {lon:.5f}",
                                "source_table": "locations",
                                "device_id": device_id,
                                "acquisition_id": acquisition_id,
                            })
                        count += 1

                    elif ts_iso and ts_unix:
                        artifacts.insert_timeline_event({
                            "event_type": "photo",
                            "timestamp": ts_iso,
                            "timestamp_unix": ts_unix,
                            "title": f"Photo: {fname}",
                            "description": os.path.relpath(fpath, dir_path),
                            "device_id": device_id,
                            "acquisition_id": acquisition_id,
                        })

                except Exception as e:
                    logger.debug(f"EXIF parse failed for {fname}: {e}")
                    continue

        artifacts.commit()
        logger.info(f"Extracted EXIF GPS from {count} photos in {dir_path}")
        return count

    def _read_exif_jpeg(self, file_path: str) -> dict:
        result = {}
        try:
            with open(file_path, "rb") as f:
                header = f.read(2)
                if header != b"\xff\xd8":
                    return result

                while True:
                    marker = f.read(2)
                    if len(marker) < 2:
                        return result
                    if marker[0] != 0xFF:
                        return result

                    length_bytes = f.read(2)
                    if len(length_bytes) < 2:
                        return result
                    length = struct.unpack(">H", length_bytes)[0]

                    if marker[1] == 0xE1:
                        data = f.read(length - 2)
                        if data[:4] == b"Exif":
                            result = self._parse_exif_data(data[6:])
                        return result
                    elif marker[1] == 0xDA:
                        return result
                    else:
                        f.seek(length - 2, 1)

        except (IOError, struct.error):
            pass
        return result

    def _parse_exif_data(self, data: bytes) -> dict:
        result = {}
        try:
            if data[:2] == b"II":
                endian = "<"
            elif data[:2] == b"MM":
                endian = ">"
            else:
                return result

            ifd0_offset = struct.unpack(endian + "I", data[4:8])[0]

            gps_offset = None
            exif_offset = None

            num_entries = struct.unpack(endian + "H", data[ifd0_offset:ifd0_offset+2])[0]
            for i in range(min(num_entries, 50)):
                entry_offset = ifd0_offset + 2 + (i * 12)
                if entry_offset + 12 > len(data):
                    break
                tag = struct.unpack(endian + "H", data[entry_offset:entry_offset+2])[0]
                if tag == self.GPS_IFD_TAG:
                    gps_offset = struct.unpack(endian + "I", data[entry_offset+8:entry_offset+12])[0]
                elif tag == self.EXIF_IFD_TAG:
                    exif_offset = struct.unpack(endian + "I", data[entry_offset+8:entry_offset+12])[0]

            if exif_offset and exif_offset < len(data) - 2:
                num = struct.unpack(endian + "H", data[exif_offset:exif_offset+2])[0]
                for i in range(min(num, 80)):
                    off = exif_offset + 2 + (i * 12)
                    if off + 12 > len(data):
                        break
                    tag = struct.unpack(endian + "H", data[off:off+2])[0]
                    if tag == self.DATE_TIME_ORIGINAL:
                        count = struct.unpack(endian + "I", data[off+4:off+8])[0]
                        val_offset = struct.unpack(endian + "I", data[off+8:off+12])[0]
                        if val_offset + count <= len(data):
                            result["datetime"] = data[val_offset:val_offset+count-1].decode("ascii", errors="replace")

            if gps_offset and gps_offset < len(data) - 2:
                gps_data = self._parse_gps_ifd(data, gps_offset, endian)
                result.update(gps_data)

        except (struct.error, IndexError):
            pass
        return result

    def _parse_gps_ifd(self, data: bytes, offset: int, endian: str) -> dict:
        result = {}
        lat_ref = lon_ref = None
        lat_vals = lon_vals = None
        altitude = None

        try:
            num = struct.unpack(endian + "H", data[offset:offset+2])[0]
            for i in range(min(num, 30)):
                off = offset + 2 + (i * 12)
                if off + 12 > len(data):
                    break
                tag = struct.unpack(endian + "H", data[off:off+2])[0]
                typ = struct.unpack(endian + "H", data[off+2:off+4])[0]
                count = struct.unpack(endian + "I", data[off+4:off+8])[0]

                if tag == self.GPS_LATITUDE_REF:
                    lat_ref = chr(data[off+8])
                elif tag == self.GPS_LONGITUDE_REF:
                    lon_ref = chr(data[off+8])
                elif tag == self.GPS_LATITUDE and typ == 5:
                    val_off = struct.unpack(endian + "I", data[off+8:off+12])[0]
                    lat_vals = self._read_rationals(data, val_off, 3, endian)
                elif tag == self.GPS_LONGITUDE and typ == 5:
                    val_off = struct.unpack(endian + "I", data[off+8:off+12])[0]
                    lon_vals = self._read_rationals(data, val_off, 3, endian)
                elif tag == self.GPS_ALTITUDE and typ == 5:
                    val_off = struct.unpack(endian + "I", data[off+8:off+12])[0]
                    alt_rat = self._read_rationals(data, val_off, 1, endian)
                    if alt_rat:
                        altitude = alt_rat[0]

            if lat_vals and lon_vals:
                lat = lat_vals[0] + lat_vals[1] / 60.0 + lat_vals[2] / 3600.0
                lon = lon_vals[0] + lon_vals[1] / 60.0 + lon_vals[2] / 3600.0
                if lat_ref == "S":
                    lat = -lat
                if lon_ref == "W":
                    lon = -lon
                result["latitude"] = lat
                result["longitude"] = lon
                if altitude is not None:
                    result["altitude"] = altitude

        except (struct.error, IndexError):
            pass
        return result

    def _read_rationals(self, data: bytes, offset: int, count: int, endian: str) -> list:
        values = []
        for i in range(count):
            off = offset + (i * 8)
            if off + 8 > len(data):
                break
            num = struct.unpack(endian + "I", data[off:off+4])[0]
            den = struct.unpack(endian + "I", data[off+4:off+8])[0]
            values.append(num / den if den != 0 else 0)
        return values


IOS_DB_PATHS = {
    "sms.db": [
        "private/var/mobile/Library/SMS/sms.db",
        "HomeDomain/Library/SMS/sms.db",
    ],
    "whatsapp": [
        "private/var/mobile/Containers/Shared/AppGroup/*/ChatStorage.sqlite",
        "AppDomainGroup-group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite",
    ],
    "call_history": [
        "private/var/mobile/Library/CallHistoryDB/CallHistory.storedata",
        "HomeDomain/Library/CallHistoryDB/CallHistory.storedata",
    ],
    "contacts": [
        "private/var/mobile/Library/AddressBook/AddressBook.sqlitedb",
        "HomeDomain/Library/AddressBook/AddressBook.sqlitedb",
    ],
    "safari": [
        "private/var/mobile/Library/Safari/History.db",
        "HomeDomain/Library/Safari/History.db",
    ],
    "locations": [
        "private/var/mobile/Library/Caches/com.apple.routined/Cache.sqlite",
        "RootDomain/Library/Caches/com.apple.routined/Cache.sqlite",
    ],
}

ITUNES_BACKUP_MANIFEST = {
    "sms.db": [
        ("HomeDomain", "Library/SMS/sms.db"),
    ],
    "whatsapp": [
        ("AppDomainGroup-group.net.whatsapp.WhatsApp.shared", "ChatStorage.sqlite"),
        ("AppDomainGroup-group.net.whatsapp.WhatsApp.shared", "Message/Media"),
    ],
    "call_history": [
        ("HomeDomain", "Library/CallHistoryDB/CallHistory.storedata"),
    ],
    "safari": [
        ("HomeDomain", "Library/Safari/History.db"),
    ],
    "locations": [
        ("RootDomain", "Library/Caches/com.apple.routined/Cache.sqlite"),
        ("HomeDomain", "Library/Caches/com.apple.routined/Cache.sqlite"),
    ],
    "contacts": [
        ("HomeDomain", "Library/AddressBook/AddressBook.sqlitedb"),
    ],
    "notes": [
        ("HomeDomain", "Library/Notes/notes.sqlite"),
    ],
    "calendar": [
        ("HomeDomain", "Library/Calendar/Calendar.sqlitedb"),
    ],
    "photos": [
        ("CameraRollDomain", "Media/DCIM"),
    ],
}


class ITunesBackupResolver:

    def __init__(self, backup_dir: str):
        self.backup_dir = backup_dir
        self.manifest_path = os.path.join(backup_dir, "Manifest.db")
        self.conn = None
        self._cache = {}

        if os.path.exists(self.manifest_path):
            self.conn = sqlite3.connect(self.manifest_path)
            self.conn.row_factory = sqlite3.Row
            logger.info(f"Opened iTunes Manifest.db at {self.manifest_path}")

            try:
                count = self.conn.execute("SELECT COUNT(*) FROM Files").fetchone()[0]
                logger.info(f"Manifest.db contains {count} file records")
            except Exception as e:
                logger.warning(f"Could not read Manifest.db: {e}")

    def is_itunes_backup(self) -> bool:
        return self.conn is not None

    def _resolve_blob(
        self, file_id: str, domain: str, relative_path: str
    ) -> Optional[str]:
        candidates = (
            os.path.join(self.backup_dir, file_id[:2], file_id),
            os.path.join(self.backup_dir, relative_path),
            os.path.join(self.backup_dir, domain, relative_path),
        )
        for cand in candidates:
            if os.path.exists(cand):
                return cand
        return None

    def find_file(self, domain: str, relative_path: str) -> Optional[str]:
        if not self.conn:
            return None

        cache_key = f"{domain}:{relative_path}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            row = self.conn.execute(
                "SELECT fileID FROM Files WHERE domain = ? AND relativePath = ? AND flags != 2",
                (domain, relative_path),
            ).fetchone()

            if row:
                file_id = row["fileID"]
                file_path = self._resolve_blob(file_id, domain, relative_path)
                if file_path:
                    self._cache[cache_key] = file_path
                    logger.info(f"Found backup file: {domain}/{relative_path} → {file_id[:8]}...")
                    return file_path
                else:
                    logger.debug(
                        f"Manifest entry exists but file missing on disk: "
                        f"{domain}/{relative_path} (fileID {file_id[:8]}...)"
                    )
        except Exception as e:
            logger.warning(f"Manifest lookup failed for {domain}/{relative_path}: {e}")

        return None

    def find_file_by_path(self, relative_path: str) -> Optional[str]:
        if not self.conn:
            return None

        try:
            row = self.conn.execute(
                "SELECT fileID, domain FROM Files WHERE relativePath = ? AND flags != 2",
                (relative_path,),
            ).fetchone()

            if row:
                file_id = row["fileID"]
                file_path = self._resolve_blob(file_id, row["domain"], relative_path)
                if file_path:
                    logger.info(f"Found: {row['domain']}/{relative_path} → {file_id[:8]}...")
                    return file_path
        except Exception as e:
            logger.warning(f"Manifest lookup by path failed: {e}")

        return None

    def find_files_like(self, domain_pattern: str, path_pattern: str) -> list[tuple[str, str]]:
        if not self.conn:
            return []

        try:
            rows = self.conn.execute(
                "SELECT fileID, domain, relativePath FROM Files WHERE domain LIKE ? AND relativePath LIKE ? AND flags != 2",
                (domain_pattern, path_pattern),
            ).fetchall()

            results = []
            for row in rows:
                file_id = row["fileID"]
                file_path = self._resolve_blob(
                    file_id, row["domain"], row["relativePath"]
                )
                if file_path:
                    results.append((file_path, f"{row['domain']}/{row['relativePath']}"))
            return results
        except Exception as e:
            logger.warning(f"Manifest pattern search failed: {e}")
            return []

    def list_domains(self) -> list[str]:
        if not self.conn:
            return []
        try:
            rows = self.conn.execute("SELECT DISTINCT domain FROM Files ORDER BY domain").fetchall()
            return [r["domain"] for r in rows]
        except Exception:
            return []

    def close(self):
        if self.conn:
            self.conn.close()


class ContactsParser:

    def parse(self, db_path: str, artifacts: ArtifactsDB, device_id: str, acquisition_id: str):
        if not os.path.exists(db_path):
            return 0

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        count = 0

        try:
            rows = conn.execute("""
                SELECT
                    p.ROWID,
                    p.First as first_name,
                    p.Last as last_name,
                    p.Organization as org,
                    p.Note as notes
                FROM ABPerson p
                ORDER BY p.First
            """).fetchall()

            for row in rows:
                name = " ".join(filter(None, [row["first_name"], row["last_name"]]))
                if not name:
                    name = row["org"] or "Unknown"

                phone = None
                try:
                    prow = conn.execute(
                        "SELECT value FROM ABMultiValue WHERE record_id = ? AND property = 3 LIMIT 1",
                        (row["ROWID"],),
                    ).fetchone()
                    if prow:
                        phone = prow["value"]
                except Exception:
                    pass

                email = None
                try:
                    erow = conn.execute(
                        "SELECT value FROM ABMultiValue WHERE record_id = ? AND property = 4 LIMIT 1",
                        (row["ROWID"],),
                    ).fetchone()
                    if erow:
                        email = erow["value"]
                except Exception:
                    pass

                contact = {
                    "source": "ios_addressbook",
                    "name": name,
                    "phone": phone,
                    "email": email,
                    "organization": row["org"],
                    "notes": row["notes"],
                    "device_id": device_id,
                    "acquisition_id": acquisition_id,
                }
                artifacts.insert_contact(contact)
                count += 1

            artifacts.commit()
            logger.info(f"Parsed {count} contacts from {db_path}")

        except Exception as e:
            logger.error(f"Contacts parsing failed: {e}")
        finally:
            conn.close()
        return count


def find_db(extraction_dir: str, candidates: list[str]) -> Optional[str]:
    import glob
    for candidate in candidates:
        if "*" in candidate:
            matches = glob.glob(os.path.join(extraction_dir, candidate))
            if matches:
                return matches[0]
        else:
            full = os.path.join(extraction_dir, candidate)
            if os.path.exists(full):
                return full
    return None


def parse_extraction(
    case_dir: str,
    extraction_dir: str,
    platform: str,
    device_id: str,
    acquisition_id: str,
) -> dict:
    artifacts = ArtifactsDB(case_dir)
    results = {}

    try:
        if platform == "ios":
            resolver = ITunesBackupResolver(extraction_dir)
            if resolver.is_itunes_backup():
                logger.info("Detected iTunes backup format - using Manifest.db resolver")
                results = _parse_ios_backup(extraction_dir, resolver, artifacts, device_id, acquisition_id)
                results["format"] = "itunes_backup"
                resolver.close()

                parsed_count = sum(v for k, v in results.items() if isinstance(v, int))
                if parsed_count == 0:
                    logger.info("Manifest.db resolver found no artifacts - falling back to brute-force scan")
                    results = _scan_and_parse_ios(extraction_dir, artifacts, device_id, acquisition_id)
                    results["format"] = "itunes_backup_bruteforce_fallback"
            else:
                results = _parse_ios(extraction_dir, artifacts, device_id, acquisition_id)
                parsed_count = sum(v for k, v in results.items() if isinstance(v, int))
                if parsed_count > 0:
                    results["format"] = "filesystem"
                else:
                    logger.info("No Manifest.db and no direct paths - scanning for SQLite databases")
                    results = _scan_and_parse_ios(extraction_dir, artifacts, device_id, acquisition_id)
                    results["format"] = "brute_force_scan"
        elif platform == "android":
            results = _parse_android(extraction_dir, artifacts, device_id, acquisition_id)
        else:
            logger.warning(f"Unknown platform: {platform}")
            results = {"error": f"Unknown platform: {platform}"}

    except Exception as e:
        logger.error(f"Parser engine failed: {e}", exc_info=True)
        results["error"] = str(e)
    finally:
        artifacts.close()

    return results


DB_SIGNATURES = {
    "sms": {"message", "handle"},
    "contacts": {"ABPerson"},
    "call_history": {"ZCALLRECORD"},
    "safari": {"history_visits", "history_items"},
    "whatsapp_ios": {"ZWAMESSAGE", "ZWACHATSESSION"},
    "notes": {"ZICCLOUDSYNCINGOBJECT"},
    "locations": {"ZRTLEARNEDLOCATIONOFINTERESTVISITMO"},
    "locations_alt": {"ZRTLEARNEDVISITMO"},
}


def _identify_sqlite_db(file_path: str) -> Optional[str]:
    try:
        with open(file_path, "rb") as f:
            header = f.read(16)
        if not header.startswith(b"SQLite"):
            return None

        conn = sqlite3.connect(file_path)
        tables = set()
        try:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            tables = {r[0] for r in rows}
        except Exception:
            conn.close()
            return None
        conn.close()

        for db_type, required_tables in DB_SIGNATURES.items():
            if required_tables.issubset(tables):
                return db_type

        return None
    except Exception:
        return None


def _scan_and_parse_ios(
    extraction_dir: str,
    artifacts: ArtifactsDB,
    device_id: str,
    acquisition_id: str,
) -> dict:
    results = {"sqlite_files_scanned": 0, "databases_identified": {}}

    sqlite_files = {}

    for root, dirs, files in os.walk(extraction_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                size = os.path.getsize(fpath)
                if size < 4096:
                    continue

                db_type = _identify_sqlite_db(fpath)
                results["sqlite_files_scanned"] += 1

                if db_type and db_type not in sqlite_files:
                    sqlite_files[db_type] = fpath
                    results["databases_identified"][db_type] = fpath
                    logger.info(f"Identified {db_type} database: {fpath}")

                    if len(sqlite_files) >= len(DB_SIGNATURES):
                        break
            except (PermissionError, OSError):
                continue

        if len(sqlite_files) >= len(DB_SIGNATURES):
            break

    logger.info(f"Scan complete: checked {results['sqlite_files_scanned']} files, "
                f"identified {len(sqlite_files)} databases: {list(sqlite_files.keys())}")

    if "sms" in sqlite_files:
        parser = IMESSAGEParser()
        count = parser.parse(sqlite_files["sms"], artifacts, device_id, acquisition_id)
        results["imessage_sms"] = count
        logger.info(f"Parsed {count} messages from SMS database")

    if "contacts" in sqlite_files:
        parser = ContactsParser()
        count = parser.parse(sqlite_files["contacts"], artifacts, device_id, acquisition_id)
        results["contacts"] = count
        logger.info(f"Parsed {count} contacts")

    if "call_history" in sqlite_files:
        parser = CallLogParser()
        count = parser.parse_ios(sqlite_files["call_history"], artifacts, device_id, acquisition_id)
        results["calls"] = count
        logger.info(f"Parsed {count} call records")

    if "safari" in sqlite_files:
        parser = SafariHistoryParser()
        count = parser.parse(sqlite_files["safari"], artifacts, device_id, acquisition_id)
        results["safari"] = count
        logger.info(f"Parsed {count} Safari history entries")

    if "whatsapp_ios" in sqlite_files:
        parser = WhatsAppParser()
        count = parser.parse_ios(sqlite_files["whatsapp_ios"], artifacts, device_id, acquisition_id)
        results["whatsapp"] = count
        logger.info(f"Parsed {count} WhatsApp messages")

    if "locations" in sqlite_files or "locations_alt" in sqlite_files:
        loc_path = sqlite_files.get("locations") or sqlite_files.get("locations_alt")
        parser = LocationParser()
        count = parser.parse_significant_locations(loc_path, artifacts, device_id, acquisition_id)
        results["locations"] = count
        logger.info(f"Parsed {count} locations")

    exif_parser = EXIFParser()
    exif_count = exif_parser.parse_directory(extraction_dir, artifacts, device_id, acquisition_id)
    if exif_count > 0:
        results["exif_locations"] = exif_count

    return results


def _parse_ios_backup(
    backup_dir: str,
    resolver: ITunesBackupResolver,
    artifacts: ArtifactsDB,
    device_id: str,
    acquisition_id: str,
) -> dict:
    results = {}

    domains = resolver.list_domains()
    results["domains_found"] = len(domains)
    logger.info(f"Backup contains {len(domains)} domains: {domains[:20]}")

    for domain, path in ITUNES_BACKUP_MANIFEST["sms.db"]:
        db_path = resolver.find_file(domain, path)
        if db_path:
            parser = IMESSAGEParser()
            results["imessage_sms"] = parser.parse(db_path, artifacts, device_id, acquisition_id)
            break

    for domain, path in ITUNES_BACKUP_MANIFEST["contacts"]:
        db_path = resolver.find_file(domain, path)
        if db_path:
            parser = ContactsParser()
            results["contacts"] = parser.parse(db_path, artifacts, device_id, acquisition_id)
            break

    for domain, path in ITUNES_BACKUP_MANIFEST["call_history"]:
        db_path = resolver.find_file(domain, path)
        if db_path:
            parser = CallLogParser()
            results["calls"] = parser.parse_ios(db_path, artifacts, device_id, acquisition_id)
            break

    for domain, path in ITUNES_BACKUP_MANIFEST["safari"]:
        db_path = resolver.find_file(domain, path)
        if db_path:
            parser = SafariHistoryParser()
            results["safari"] = parser.parse(db_path, artifacts, device_id, acquisition_id)
            break

    for domain, path in ITUNES_BACKUP_MANIFEST["whatsapp"]:
        db_path = resolver.find_file(domain, path)
        if db_path:
            parser = WhatsAppParser()
            results["whatsapp"] = parser.parse_ios(db_path, artifacts, device_id, acquisition_id)
            break

    if "whatsapp" not in results:
        wa_files = resolver.find_files_like("%whatsapp%", "ChatStorage.sqlite")
        if wa_files:
            parser = WhatsAppParser()
            results["whatsapp"] = parser.parse_ios(wa_files[0][0], artifacts, device_id, acquisition_id)

    for domain, path in ITUNES_BACKUP_MANIFEST["locations"]:
        db_path = resolver.find_file(domain, path)
        if db_path:
            parser = LocationParser()
            results["locations"] = parser.parse_significant_locations(
                db_path, artifacts, device_id, acquisition_id
            )
            break

    exif_parser = EXIFParser()
    exif_count = exif_parser.parse_directory(backup_dir, artifacts, device_id, acquisition_id)
    if exif_count > 0:
        results["exif_locations"] = exif_count

    return results


def _parse_ios(extraction_dir: str, artifacts: ArtifactsDB,
               device_id: str, acquisition_id: str) -> dict:
    results = {}

    sms_path = find_db(extraction_dir, IOS_DB_PATHS["sms.db"])
    if sms_path:
        parser = IMESSAGEParser()
        results["imessage_sms"] = parser.parse(sms_path, artifacts, device_id, acquisition_id)

    wa_path = find_db(extraction_dir, IOS_DB_PATHS["whatsapp"])
    if wa_path:
        parser = WhatsAppParser()
        results["whatsapp"] = parser.parse_ios(wa_path, artifacts, device_id, acquisition_id)

    call_path = find_db(extraction_dir, IOS_DB_PATHS["call_history"])
    if call_path:
        parser = CallLogParser()
        results["calls"] = parser.parse_ios(call_path, artifacts, device_id, acquisition_id)

    contacts_path = find_db(extraction_dir, IOS_DB_PATHS["contacts"])
    if contacts_path:
        parser = ContactsParser()
        results["contacts"] = parser.parse(contacts_path, artifacts, device_id, acquisition_id)

    safari_path = find_db(extraction_dir, IOS_DB_PATHS["safari"])
    if safari_path:
        parser = SafariHistoryParser()
        results["safari"] = parser.parse(safari_path, artifacts, device_id, acquisition_id)

    loc_path = find_db(extraction_dir, IOS_DB_PATHS["locations"])
    if loc_path:
        parser = LocationParser()
        results["locations"] = parser.parse_significant_locations(
            loc_path, artifacts, device_id, acquisition_id
        )

    dcim_candidates = [
        os.path.join(extraction_dir, "private/var/mobile/Media/DCIM"),
        os.path.join(extraction_dir, "Media/DCIM"),
    ]
    for dcim in dcim_candidates:
        if os.path.isdir(dcim):
            exif_parser = EXIFParser()
            exif_count = exif_parser.parse_directory(dcim, artifacts, device_id, acquisition_id)
            if exif_count > 0:
                results["exif_locations"] = exif_count
            break

    return results


def _parse_android(extraction_dir: str, artifacts: ArtifactsDB,
                   device_id: str, acquisition_id: str) -> dict:
    results = {}

    wa_candidates = [
        "WhatsApp/Databases/msgstore.db",
        "data/data/com.whatsapp/databases/msgstore.db",
        "media/0/WhatsApp/Databases/msgstore.db",
    ]
    wa_path = find_db(extraction_dir, wa_candidates)
    if wa_path:
        parser = WhatsAppParser()
        results["whatsapp"] = parser.parse_android(wa_path, artifacts, device_id, acquisition_id)

    for photo_dir_name in ["DCIM", "Pictures"]:
        photo_dir = os.path.join(extraction_dir, photo_dir_name)
        if os.path.isdir(photo_dir):
            exif_parser = EXIFParser()
            exif_count = exif_parser.parse_directory(photo_dir, artifacts, device_id, acquisition_id)
            if exif_count > 0:
                results.setdefault("exif_locations", 0)
                results["exif_locations"] += exif_count

    return results

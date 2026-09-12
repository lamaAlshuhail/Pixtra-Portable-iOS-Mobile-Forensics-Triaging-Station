import json
import logging
import os
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Optional

logger = logging.getLogger("pixtra.entities")


class EntityExtractor:

    def __init__(self, artifacts_db_path: str):
        self.conn = sqlite3.connect(artifacts_db_path)
        self.conn.row_factory = sqlite3.Row

        self._entity_cache: dict[str, int] = {}

    def extract_all(self) -> dict:
        results = {}

        results["people"] = self._extract_people()
        results["locations"] = self._extract_locations()
        results["apps"] = self._extract_apps()
        results["edges"] = self._build_edges()

        self.conn.commit()
        return results

    def _extract_people(self) -> int:
        count = 0

        contacts = self.conn.execute(
            "SELECT DISTINCT name, phone, email FROM contacts WHERE name IS NOT NULL"
        ).fetchall()
        for c in contacts:
            identifier = c["phone"] or c["email"] or c["name"]
            self._upsert_entity("person", c["name"], identifier)
            count += 1

        senders = self.conn.execute("""
            SELECT sender as identifier, sender_name as name, COUNT(*) as msg_count,
                   MIN(timestamp) as first_seen, MAX(timestamp) as last_seen
            FROM messages
            WHERE sender IS NOT NULL
            GROUP BY sender
        """).fetchall()
        for s in senders:
            name = s["name"] or s["identifier"]
            eid = self._upsert_entity("person", name, s["identifier"])
            self.conn.execute(
                "UPDATE entities SET occurrence_count = ?, first_seen = ?, last_seen = ? WHERE id = ?",
                (s["msg_count"], s["first_seen"], s["last_seen"], eid),
            )
            count += 1

        callers = self.conn.execute("""
            SELECT number, name, COUNT(*) as call_count,
                   MIN(timestamp) as first_seen, MAX(timestamp) as last_seen
            FROM calls
            WHERE number IS NOT NULL
            GROUP BY number
        """).fetchall()
        for c in callers:
            name = c["name"] or c["number"]
            eid = self._upsert_entity("person", name, c["number"])
            self.conn.execute(
                """UPDATE entities SET
                   occurrence_count = MAX(occurrence_count, ?),
                   first_seen = MIN(COALESCE(first_seen, ?), ?),
                   last_seen = MAX(COALESCE(last_seen, ?), ?)
                   WHERE id = ?""",
                (c["call_count"], c["first_seen"], c["first_seen"],
                 c["last_seen"], c["last_seen"], eid),
            )
            count += 1

        self.conn.commit()
        logger.info(f"Extracted {count} person entities")
        return count

    def _extract_locations(self) -> int:
        count = 0

        locations = self.conn.execute("""
            SELECT
                ROUND(latitude, 3) as lat_r,
                ROUND(longitude, 3) as lon_r,
                COUNT(*) as visit_count,
                MIN(timestamp) as first_seen,
                MAX(timestamp) as last_seen,
                label
            FROM locations
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            GROUP BY lat_r, lon_r
        """).fetchall()

        for loc in locations:
            name = loc["label"] or f"{loc['lat_r']}, {loc['lon_r']}"
            identifier = f"{loc['lat_r']},{loc['lon_r']}"
            eid = self._upsert_entity("location", name, identifier)
            self.conn.execute(
                "UPDATE entities SET occurrence_count = ?, first_seen = ?, last_seen = ? WHERE id = ?",
                (loc["visit_count"], loc["first_seen"], loc["last_seen"], eid),
            )
            count += 1

        wifi = self.conn.execute("""
            SELECT ssid, bssid, last_joined as first_seen
            FROM wifi_networks WHERE ssid IS NOT NULL
        """).fetchall()
        for w in wifi:
            eid = self._upsert_entity("location", f"WiFi: {w['ssid']}", w["bssid"] or w["ssid"])
            count += 1

        self.conn.commit()
        logger.info(f"Extracted {count} location entities")
        return count

    def _extract_apps(self) -> int:
        count = 0
        apps = self.conn.execute(
            "SELECT DISTINCT bundle_id, app_name FROM installed_apps WHERE app_name IS NOT NULL"
        ).fetchall()
        for a in apps:
            self._upsert_entity("app", a["app_name"], a["bundle_id"])
            count += 1

        self.conn.commit()
        logger.info(f"Extracted {count} app entities")
        return count

    def _build_edges(self) -> int:
        count = 0

        chats = self.conn.execute("""
            SELECT chat_id, GROUP_CONCAT(DISTINCT sender) as senders
            FROM messages
            WHERE sender IS NOT NULL AND chat_id IS NOT NULL
            GROUP BY chat_id
            HAVING COUNT(DISTINCT sender) > 1
        """).fetchall()

        for chat in chats:
            senders = [s for s in (chat["senders"] or "").split(",") if s]
            for i in range(len(senders)):
                for j in range(i + 1, len(senders)):
                    eid_a = self._entity_cache.get(senders[i])
                    eid_b = self._entity_cache.get(senders[j])
                    if eid_a and eid_b:
                        self._upsert_edge(eid_a, eid_b, "co_chat", 1.0)
                        count += 1

        direct_msgs = self.conn.execute("""
            SELECT
                sender, recipient, COUNT(*) as msg_count,
                MIN(timestamp) as first_msg, MAX(timestamp) as last_msg
            FROM messages
            WHERE sender IS NOT NULL AND recipient IS NOT NULL
            GROUP BY sender, recipient
        """).fetchall()

        for dm in direct_msgs:
            eid_a = self._entity_cache.get(dm["sender"])
            eid_b = self._entity_cache.get(dm["recipient"])
            if eid_a and eid_b:
                self._upsert_edge(
                    eid_a, eid_b, "messaged",
                    weight=min(dm["msg_count"] / 10.0, 10.0),
                    first_occ=dm["first_msg"],
                    last_occ=dm["last_msg"],
                )
                count += 1

        call_edges = self.conn.execute("""
            SELECT number, direction, COUNT(*) as call_count,
                   MIN(timestamp) as first_call, MAX(timestamp) as last_call
            FROM calls
            WHERE number IS NOT NULL
            GROUP BY number
        """).fetchall()

        owner_id = self._entity_cache.get("__owner__")
        if not owner_id:
            owner_id = self._upsert_entity("person", "Device Owner", "__owner__")

        for ce in call_edges:
            eid = self._entity_cache.get(ce["number"])
            if eid and owner_id:
                self._upsert_edge(
                    owner_id, eid, "called",
                    weight=min(ce["call_count"] / 5.0, 10.0),
                    first_occ=ce["first_call"],
                    last_occ=ce["last_call"],
                )
                count += 1

        temporal = self.conn.execute("""
            WITH ordered_msgs AS (
                SELECT sender, timestamp_unix,
                       LAG(sender) OVER (ORDER BY timestamp_unix) as prev_sender,
                       LAG(timestamp_unix) OVER (ORDER BY timestamp_unix) as prev_ts
                FROM messages
                WHERE sender IS NOT NULL AND timestamp_unix > 0
            )
            SELECT person_a, person_b, COUNT(*) as proximity_count
            FROM (
                SELECT prev_sender as person_a, sender as person_b
                FROM ordered_msgs
                WHERE prev_sender IS NOT NULL
                  AND sender != prev_sender
                  AND (timestamp_unix - prev_ts) <= 300
            )
            GROUP BY person_a, person_b
            HAVING proximity_count > 3
        """).fetchall()

        for t in temporal:
            eid_a = self._entity_cache.get(t["person_a"])
            eid_b = self._entity_cache.get(t["person_b"])
            if eid_a and eid_b:
                self._upsert_edge(eid_a, eid_b, "temporal_proximity",
                                  weight=min(t["proximity_count"] / 10.0, 5.0))
                count += 1

        self.conn.commit()
        logger.info(f"Built {count} entity edges")
        return count


    def _upsert_entity(self, entity_type: str, name: str, identifier: str) -> int:
        if identifier in self._entity_cache:
            return self._entity_cache[identifier]

        row = self.conn.execute(
            "SELECT id FROM entities WHERE identifier = ? AND entity_type = ?",
            (identifier, entity_type),
        ).fetchone()

        if row:
            self._entity_cache[identifier] = row["id"]
            return row["id"]

        cursor = self.conn.execute(
            "INSERT INTO entities (entity_type, name, identifier) VALUES (?, ?, ?)",
            (entity_type, name, identifier),
        )
        eid = cursor.lastrowid
        self._entity_cache[identifier] = eid
        return eid

    def _upsert_edge(self, source_id: int, target_id: int, relationship: str,
                     weight: float = 1.0, first_occ: str = None, last_occ: str = None):
        existing = self.conn.execute(
            """SELECT id, weight FROM entity_edges
               WHERE source_entity_id = ? AND target_entity_id = ? AND relationship = ?""",
            (source_id, target_id, relationship),
        ).fetchone()

        if existing:
            self.conn.execute(
                "UPDATE entity_edges SET weight = weight + ? WHERE id = ?",
                (weight, existing["id"]),
            )
        else:
            self.conn.execute(
                """INSERT INTO entity_edges
                   (source_entity_id, target_entity_id, relationship, weight, first_occurrence, last_occurrence)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (source_id, target_id, relationship, weight, first_occ, last_occ),
            )

    def get_graph_json(self) -> dict:
        nodes = []
        entities = self.conn.execute("SELECT * FROM entities ORDER BY occurrence_count DESC").fetchall()
        for e in entities:
            nodes.append({
                "id": e["id"],
                "type": e["entity_type"],
                "name": e["name"],
                "identifier": e["identifier"],
                "occurrences": e["occurrence_count"],
                "first_seen": e["first_seen"],
                "last_seen": e["last_seen"],
            })

        edges = []
        edge_rows = self.conn.execute("SELECT * FROM entity_edges").fetchall()
        for e in edge_rows:
            edges.append({
                "source": e["source_entity_id"],
                "target": e["target_entity_id"],
                "relationship": e["relationship"],
                "weight": e["weight"],
                "first_occurrence": e["first_occurrence"],
                "last_occurrence": e["last_occurrence"],
            })

        return {"nodes": nodes, "edges": edges}

    def close(self):
        self.conn.close()


def extract_entities(case_dir: str) -> dict:
    db_path = os.path.join(case_dir, "artifacts.db")
    if not os.path.exists(db_path):
        return {"error": "artifacts.db not found - run parser first"}

    extractor = EntityExtractor(db_path)
    try:
        results = extractor.extract_all()
        graph = extractor.get_graph_json()
        results["graph"] = graph
        return results
    finally:
        extractor.close()


def get_entity_graph(case_dir: str) -> dict:
    db_path = os.path.join(case_dir, "artifacts.db")
    if not os.path.exists(db_path):
        return {"nodes": [], "edges": []}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    nodes = []
    for e in conn.execute("SELECT * FROM entities ORDER BY occurrence_count DESC").fetchall():
        nodes.append({
            "id": e["id"],
            "type": e["entity_type"],
            "name": e["name"],
            "identifier": e["identifier"],
            "occurrences": e["occurrence_count"],
            "first_seen": e["first_seen"],
            "last_seen": e["last_seen"],
        })

    edges = []
    for e in conn.execute("SELECT * FROM entity_edges").fetchall():
        edges.append({
            "source": e["source_entity_id"],
            "target": e["target_entity_id"],
            "relationship": e["relationship"],
            "weight": e["weight"],
        })

    conn.close()
    return {"nodes": nodes, "edges": edges}

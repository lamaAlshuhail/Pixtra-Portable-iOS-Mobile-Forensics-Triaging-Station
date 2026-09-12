#!/usr/bin/env python3

import argparse
import glob
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional


_THIS = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_THIS)
_CANONICAL_CASES = os.environ.get(
    "PIXTRA_CASE_STORAGE", os.path.join(_BACKEND_ROOT, "data", "cases")
)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


_APP_DOMAIN = "AppDomain-com.openai.chat"
_REL_DIR = os.path.join("Library", "Application Support")
_MAC_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)


def _mac_to_iso(secs) -> Optional[str]:
    if secs is None:
        return None
    try:
        return (_MAC_EPOCH + timedelta(seconds=float(secs))).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _unix_to_iso(secs) -> Optional[str]:
    if secs is None:
        return None
    try:
        return datetime.fromtimestamp(float(secs), timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _resolve_artifacts_db(case_id: str) -> str:
    candidates = [
        os.environ.get("PIXTRA_CASE_STORAGE"),
        _CANONICAL_CASES,
        os.path.join(_BACKEND_ROOT, "data", "cases"),
    ]
    for root in candidates:
        if not root:
            continue
        path = os.path.join(root, case_id, "artifacts.db")
        if os.path.isfile(path):
            return path
    listed = "\n  ".join(
        os.path.join(c, case_id, "artifacts.db")
        for c in candidates if c
    )
    raise SystemExit(
        f"artifacts.db not found for case={case_id}. Tried:\n  {listed}"
    )


def _resolve_chatgpt_root(acq_id: str) -> str:
    from app.services.database import get_acquisition

    acq = get_acquisition(acq_id)
    if not acq:
        raise SystemExit(f"Acquisition {acq_id} not found")
    output_path = acq.get("output_path")
    if not output_path:
        raise SystemExit("Acquisition has no output_path")
    candidate = os.path.join(output_path, _APP_DOMAIN, _REL_DIR)
    if os.path.isdir(candidate):
        return candidate
    raise SystemExit(
        f"ChatGPT sandbox not found. Looked at:\n  {candidate}"
    )


def _walk_conversation_files(chatgpt_root: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for entry in sorted(os.listdir(chatgpt_root)):
        if not entry.startswith("conversations-v3-"):
            continue
        account_uuid = entry[len("conversations-v3-"):]
        folder = os.path.join(chatgpt_root, entry)
        if not os.path.isdir(folder):
            continue
        for j in sorted(glob.glob(os.path.join(folder, "*.json"))):
            pairs.append((account_uuid, j))
    return pairs


def _render_message_payload(inner: dict) -> dict:
    out: dict = {
        "content_text": "",
        "content_type": "unknown",
        "image_assets": [],
        "code_language": None,
    }
    if not isinstance(inner, dict):
        out["content_text"] = ""
        return out

    ctype = inner.get("content_type") or "text"
    out["content_type"] = ctype
    pieces: list[str] = []

    if ctype == "text":
        for p in inner.get("parts") or []:
            if isinstance(p, str):
                pieces.append(p)

    elif ctype == "multimodal_text":
        for p in inner.get("parts") or []:
            if isinstance(p, str):
                pieces.append(p)
            elif isinstance(p, dict):
                p_type = p.get("content_type")
                if p_type == "image_asset_pointer":
                    out["image_assets"].append({
                        "asset_pointer": p.get("asset_pointer"),
                        "width": p.get("width"),
                        "height": p.get("height"),
                        "size_bytes": p.get("size_bytes"),
                    })
                elif isinstance(p.get("text"), str):
                    pieces.append(p["text"])
                else:
                    pieces.append(json.dumps(p, ensure_ascii=False))

    elif ctype == "code":
        out["code_language"] = inner.get("language")
        text = inner.get("text")
        if isinstance(text, str):
            pieces.append(text)
        else:
            for p in inner.get("parts") or []:
                if isinstance(p, str):
                    pieces.append(p)

    elif ctype == "thoughts":
        if inner.get("parts"):
            for p in inner.get("parts") or []:
                if isinstance(p, str):
                    pieces.append(p)
        elif isinstance(inner.get("thoughts"), list):
            for t in inner["thoughts"]:
                if not isinstance(t, dict):
                    continue
                summary = t.get("summary") or ""
                body = t.get("content") or ""
                blob = []
                if summary:
                    blob.append(f"[{summary}]")
                if body:
                    blob.append(str(body))
                if blob:
                    pieces.append("\n".join(blob))

    elif ctype == "reasoning_recap":
        if inner.get("parts"):
            for p in inner.get("parts") or []:
                if isinstance(p, str):
                    pieces.append(p)
        elif isinstance(inner.get("content"), str):
            pieces.append(inner["content"])
        elif isinstance(inner.get("text"), str):
            pieces.append(inner["text"])

    elif ctype == "execution_output":
        if isinstance(inner.get("text"), str):
            pieces.append(inner["text"])
        else:
            for p in inner.get("parts") or []:
                if isinstance(p, str):
                    pieces.append(p)

    elif ctype == "tether_browsing_display":
        title = inner.get("title")
        url = inner.get("url")
        if title:
            pieces.append(str(title))
        if url:
            pieces.append(str(url))
        if not pieces:
            pieces.append(json.dumps(inner, ensure_ascii=False))

    elif ctype == "tether_quote":
        for k in ("title", "url", "text"):
            v = inner.get(k)
            if v:
                pieces.append(str(v))

    elif ctype == "system_error":
        msg = inner.get("message") or inner.get("text") or ""
        if msg:
            pieces.append(str(msg))
        else:
            pieces.append(json.dumps(inner, ensure_ascii=False))

    else:
        pieces.append(json.dumps(inner, ensure_ascii=False, indent=2))

    out["content_text"] = "\n".join(pieces)
    return out


def _linearize_thread(conv_data: dict) -> list[dict]:
    tree = conv_data.get("tree") or {}
    storage = tree.get("storage") or []
    leaf_id = conv_data.get("current_leaf_node_id")

    nodes: dict[str, dict] = {}
    i = 0
    while i + 1 < len(storage):
        nid = storage[i]
        node = storage[i + 1]
        if isinstance(nid, str) and isinstance(node, dict):
            nodes[nid] = node
        i += 2

    if not leaf_id or leaf_id not in nodes:
        return []

    chain: list[str] = []
    current = leaf_id
    seen: set[str] = set()
    while current and current in nodes and current not in seen:
        seen.add(current)
        chain.append(current)
        current = nodes[current].get("parent")
    chain.reverse()

    messages: list[dict] = []
    for nid in chain:
        node = nodes[nid]
        wrapper = node.get("content")
        if not isinstance(wrapper, dict):
            continue
        author = wrapper.get("author") or {}
        if not isinstance(author, dict):
            continue
        role = author.get("role")
        if not role:
            continue

        inner = wrapper.get("content") or {}
        if isinstance(inner, dict) and inner.get("content_type") == "model_editable_context":
            continue

        rendered = _render_message_payload(inner if isinstance(inner, dict) else {})

        metadata = wrapper.get("metadata")
        model_slug = (
            metadata.get("model_slug")
            if isinstance(metadata, dict) else None
        )
        create_time = _unix_to_iso(wrapper.get("create_time"))
        tool_name = author.get("name") if role == "tool" else None

        messages.append({
            "role": role,
            "model_slug": model_slug,
            "create_time": create_time,
            "content_text": rendered["content_text"],
            "content_type": rendered["content_type"],
            "image_assets": rendered["image_assets"],
            "code_language": rendered["code_language"],
            "tool_name": tool_name,
            "raw_node": node,
        })
    return messages


def _ensure_schema(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(ai_conversations)")
    existing_cols = {row[1] for row in cur.fetchall()}
    REQUIRED = {
        "conversation_uuid", "account_uuid", "is_do_not_remember",
        "is_temporary_chat", "default_model", "message_count",
    }
    if existing_cols and not REQUIRED.issubset(existing_cols):
        print(
            "[parse_chatgpt] migrating old ai_conversations schema "
            "→ dropping and recreating"
        )
        conn.execute("DROP TABLE IF EXISTS ai_conversations")
        conn.execute("DROP TABLE IF EXISTS ai_messages")
        conn.commit()

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ai_conversations (
          id INTEGER PRIMARY KEY,
          acquisition_id TEXT,
          app TEXT,
          account_uuid TEXT,
          conversation_uuid TEXT,
          remote_id TEXT,
          title TEXT,
          creation_date TEXT,
          modification_date TEXT,
          is_archived INTEGER,
          is_do_not_remember INTEGER,
          is_temporary_chat INTEGER,
          is_study_mode INTEGER,
          default_model TEXT,
          custom_instructions_user TEXT,
          custom_instructions_model TEXT,
          message_count INTEGER,
          total_chars INTEGER,
          file_size INTEGER,
          file_path TEXT
        );

        CREATE TABLE IF NOT EXISTS ai_messages (
          id INTEGER PRIMARY KEY,
          acquisition_id TEXT,
          conversation_uuid TEXT,
          seq INTEGER,
          role TEXT,
          model_slug TEXT,
          create_time TEXT,
          content_text TEXT,
          content_type TEXT,
          raw_node_json TEXT,
          image_assets_json TEXT,
          code_language TEXT,
          tool_name TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_ai_messages_conv
          ON ai_messages(conversation_uuid);
        CREATE INDEX IF NOT EXISTS idx_ai_conv_acq
          ON ai_conversations(acquisition_id);
        """
    )

    msg_cols = {
        row[1] for row in conn.execute(
            "PRAGMA table_info(ai_messages)"
        ).fetchall()
    }
    for col_name, col_type in (
        ("content_type", "TEXT"),
        ("raw_node_json", "TEXT"),
        ("image_assets_json", "TEXT"),
        ("code_language", "TEXT"),
        ("tool_name", "TEXT"),
    ):
        if col_name not in msg_cols:
            conn.execute(
                f"ALTER TABLE ai_messages ADD COLUMN {col_name} {col_type}"
            )
    conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--case", required=True)
    parser.add_argument("--acquisition", required=True)
    args = parser.parse_args()

    artifacts_db = _resolve_artifacts_db(args.case)
    chatgpt_root = _resolve_chatgpt_root(args.acquisition)
    output_path_root = os.path.dirname(os.path.dirname(chatgpt_root))
    print(f"[parse_chatgpt] artifacts.db: {artifacts_db}")
    print(f"[parse_chatgpt] sandbox root: {chatgpt_root}")

    pairs = _walk_conversation_files(chatgpt_root)
    if not pairs:
        print("[parse_chatgpt] No conversation JSONs found - nothing to do.")
        return 0

    conv_rows: list[tuple] = []
    msg_rows: list[tuple] = []
    accounts: set[str] = set()
    total_messages = 0
    total_chars = 0

    for account_uuid, json_path in pairs:
        accounts.add(account_uuid)
        try:
            file_size = os.path.getsize(json_path)
        except OSError:
            file_size = 0
        try:
            with open(json_path, "r", encoding="utf-8") as fh:
                conv = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[parse_chatgpt] WARN skipping {json_path}: {exc}")
            continue

        config = conv.get("configuration") or {}
        custom = config.get("custom_instructions") or {}

        messages = _linearize_thread(conv)
        msg_count = len(messages)
        chars = sum(len(m.get("content_text") or "") for m in messages)
        total_messages += msg_count
        total_chars += chars

        rel_path = (
            os.path.relpath(json_path, output_path_root)
            if output_path_root and os.path.isdir(output_path_root)
            else json_path
        ).replace("\\", "/")

        conv_uuid = conv.get("id") or os.path.splitext(os.path.basename(json_path))[0]
        conv_rows.append((
            args.acquisition,
            "chatgpt",
            account_uuid,
            conv_uuid,
            conv.get("remote_id"),
            conv.get("title") or "",
            _mac_to_iso(conv.get("creation_date")),
            _mac_to_iso(conv.get("modification_date")),
            1 if conv.get("is_archived") else 0,
            1 if conv.get("is_do_not_remember") else 0,
            1 if conv.get("is_temporary_chat") else 0,
            1 if conv.get("is_study_mode") else 0,
            config.get("default_model") or "",
            custom.get("about_user_message") or "",
            custom.get("about_model_message") or "",
            msg_count,
            chars,
            file_size,
            rel_path,
        ))
        for seq, m in enumerate(messages):
            msg_rows.append((
                args.acquisition,
                conv_uuid,
                seq,
                m["role"],
                m["model_slug"],
                m["create_time"],
                m["content_text"],
                m["content_type"],
                json.dumps(m["raw_node"], ensure_ascii=False),
                json.dumps(m["image_assets"], ensure_ascii=False),
                m["code_language"],
                m["tool_name"],
            ))

    conn = sqlite3.connect(artifacts_db)
    try:
        _ensure_schema(conn)
        conn.execute(
            "DELETE FROM ai_conversations WHERE acquisition_id = ?",
            (args.acquisition,),
        )
        conn.execute(
            "DELETE FROM ai_messages WHERE acquisition_id = ?",
            (args.acquisition,),
        )
        conn.executemany(
            """
            INSERT INTO ai_conversations (
              acquisition_id, app, account_uuid, conversation_uuid,
              remote_id, title, creation_date, modification_date,
              is_archived, is_do_not_remember, is_temporary_chat,
              is_study_mode, default_model,
              custom_instructions_user, custom_instructions_model,
              message_count, total_chars, file_size, file_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            conv_rows,
        )
        conn.executemany(
            """
            INSERT INTO ai_messages (
              acquisition_id, conversation_uuid, seq, role,
              model_slug, create_time, content_text,
              content_type, raw_node_json, image_assets_json,
              code_language, tool_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            msg_rows,
        )
        conn.commit()
    finally:
        conn.close()

    accounts_str = ", ".join(sorted(accounts)) if accounts else "(none)"
    print(
        f"Parsed {len(conv_rows)} conversations, "
        f"{total_messages} messages, {total_chars} chars from {accounts_str}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

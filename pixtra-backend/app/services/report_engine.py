import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("pixtra.report")


class ReportConfig:

    def __init__(
        self,
        title: str = "Forensic Examination Report",
        examiner: str = "",
        organization: str = "",
        format: str = "html",
        sections: list[str] = None,
        logo_path: Optional[str] = None,
    ):
        self.title = title
        self.examiner = examiner
        self.organization = organization
        self.format = format
        self.sections = sections or [
            "case_summary",
            "device_info",
            "methodology",
            "evidence_summary",
            "messages",
            "contacts",
            "calls",
            "timeline",
            "entity_graph",
            "examiner_notes",
            "hash_verification",
            "chain_of_custody",
        ]
        self.logo_path = logo_path


def generate_report(
    case_id: str,
    case_dir: str,
    db_path: str,
    config: ReportConfig,
) -> dict:
    start = datetime.utcnow()

    case_db = sqlite3.connect(db_path)
    case_db.row_factory = sqlite3.Row

    case = dict(case_db.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone() or {})
    devices = [dict(r) for r in case_db.execute("SELECT * FROM devices WHERE case_id = ?", (case_id,)).fetchall()]
    acquisitions = [dict(r) for r in case_db.execute("SELECT * FROM acquisitions WHERE case_id = ?", (case_id,)).fetchall()]
    custody = [dict(r) for r in case_db.execute("SELECT * FROM custody_log WHERE case_id = ? ORDER BY timestamp ASC", (case_id,)).fetchall()]

    hash_entries = []
    for acq in acquisitions:
        rows = case_db.execute("SELECT * FROM hash_manifest WHERE acquisition_id = ?", (acq["id"],)).fetchall()
        hash_entries.extend([dict(r) for r in rows])

    case_db.close()

    artifacts_path = os.path.join(case_dir, "artifacts.db")
    messages = []
    contacts = []
    calls = []
    timeline = []
    entities = []
    entity_edges = []
    notes = []
    evidence_counts = {}

    if os.path.exists(artifacts_path):
        adb = sqlite3.connect(artifacts_path)
        adb.row_factory = sqlite3.Row

        for table in ["messages", "contacts", "calls", "locations", "web_history",
                       "wifi_networks", "installed_apps", "keychain_items"]:
            try:
                count = adb.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                evidence_counts[table] = count
            except sqlite3.OperationalError:
                evidence_counts[table] = 0

        try:
            messages = [dict(r) for r in adb.execute(
                "SELECT * FROM messages ORDER BY timestamp_unix ASC LIMIT 500"
            ).fetchall()]
        except Exception:
            pass

        try:
            contacts = [dict(r) for r in adb.execute(
                "SELECT * FROM contacts ORDER BY name LIMIT 200"
            ).fetchall()]
        except Exception:
            pass

        try:
            calls = [dict(r) for r in adb.execute(
                "SELECT * FROM calls ORDER BY timestamp_unix DESC LIMIT 200"
            ).fetchall()]
        except Exception:
            pass

        try:
            timeline = [dict(r) for r in adb.execute(
                "SELECT * FROM timeline_events ORDER BY timestamp_unix DESC LIMIT 500"
            ).fetchall()]
        except Exception:
            pass

        try:
            entities = [dict(r) for r in adb.execute(
                "SELECT * FROM entities ORDER BY occurrence_count DESC"
            ).fetchall()]
        except Exception:
            pass

        try:
            entity_edges = [dict(r) for r in adb.execute(
                "SELECT * FROM entity_edges"
            ).fetchall()]
        except Exception:
            pass

        try:
            adb.execute("SELECT 1 FROM examiner_notes LIMIT 1")
            notes = [dict(r) for r in adb.execute(
                "SELECT * FROM examiner_notes ORDER BY updated_at DESC"
            ).fetchall()]
        except Exception:
            pass

        adb.close()

    html = _build_html_report(
        config=config,
        case=case,
        devices=devices,
        acquisitions=acquisitions,
        custody=custody,
        hash_entries=hash_entries,
        evidence_counts=evidence_counts,
        messages=messages,
        contacts=contacts,
        calls=calls,
        timeline=timeline,
        entities=entities,
        entity_edges=entity_edges,
        notes=notes,
    )

    reports_dir = os.path.join(case_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    html_path = os.path.join(reports_dir, f"report_{timestamp}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    result = {
        "format": "html",
        "output_path": html_path,
        "sections_included": config.sections,
        "generation_time_ms": int((datetime.utcnow() - start).total_seconds() * 1000),
    }

    if config.format == "pdf":
        pdf_path = os.path.join(reports_dir, f"report_{timestamp}.pdf")
        try:
            from weasyprint import HTML as WeasyprintHTML
            WeasyprintHTML(string=html).write_pdf(pdf_path)
            result["format"] = "pdf"
            result["output_path"] = pdf_path
            result["html_path"] = html_path
            logger.info(f"PDF report generated: {pdf_path}")
        except ImportError:
            logger.warning("weasyprint not installed - falling back to HTML. Install: pip install weasyprint")
            result["pdf_error"] = "weasyprint not installed"
        except Exception as e:
            logger.error(f"PDF generation failed: {e}")
            result["pdf_error"] = str(e)

    logger.info(f"Report generated: {result['output_path']} in {result['generation_time_ms']}ms")
    return result


def _esc(text) -> str:
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _build_html_report(
    config: ReportConfig,
    case: dict,
    devices: list,
    acquisitions: list,
    custody: list,
    hash_entries: list,
    evidence_counts: dict,
    messages: list,
    contacts: list,
    calls: list,
    timeline: list,
    entities: list,
    entity_edges: list,
    notes: list,
) -> str:

    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    sections_html = []

    if "case_summary" in config.sections:
        sections_html.append(f"""
        <section class="section">
            <h2>1. Case Summary</h2>
            <table class="info-table">
                <tr><td class="label">Case Number</td><td>{_esc(case.get('case_number'))}</td></tr>
                <tr><td class="label">Case Name</td><td>{_esc(case.get('name'))}</td></tr>
                <tr><td class="label">Examiner</td><td>{_esc(case.get('examiner'))}</td></tr>
                <tr><td class="label">Status</td><td>{_esc(case.get('status', 'active').upper())}</td></tr>
                <tr><td class="label">Created</td><td>{_esc(case.get('created_at', '')[:19])}</td></tr>
                <tr><td class="label">Devices</td><td>{case.get('device_count', 0)}</td></tr>
                <tr><td class="label">Total Evidence Size</td><td>{_format_bytes(case.get('total_size_bytes', 0))}</td></tr>
                <tr><td class="label">Report Generated</td><td>{generated_at}</td></tr>
            </table>
            {f'<p class="notes">{_esc(case.get("notes"))}</p>' if case.get('notes') else ''}
        </section>
        """)

    if "device_info" in config.sections and devices:
        dev_rows = ""
        for d in devices:
            dev_rows += f"""<tr>
                <td>{_esc(d.get('model_name') or d.get('model'))}</td>
                <td>{_esc(d.get('platform', '').upper())}</td>
                <td>{_esc(d.get('chipset'))}</td>
                <td>{_esc(d.get('os_version'))}</td>
                <td><code>{_esc(d.get('serial'))}</code></td>
                <td>{_esc(d.get('acquisition_status', ' - '))}</td>
            </tr>"""

        sections_html.append(f"""
        <section class="section">
            <h2>2. Device Information</h2>
            <table class="data-table">
                <thead><tr>
                    <th>Model</th><th>Platform</th><th>Chipset</th>
                    <th>OS Version</th><th>Serial</th><th>Acq. Status</th>
                </tr></thead>
                <tbody>{dev_rows}</tbody>
            </table>
        </section>
        """)

    if "methodology" in config.sections:
        acq_rows = ""
        for a in acquisitions:
            acq_rows += f"""<tr>
                <td><code>{_esc(a.get('id', '')[:8])}</code></td>
                <td>{_esc(a.get('method'))}</td>
                <td>{_esc(a.get('status'))}</td>
                <td>{a.get('files_extracted', 0):,}</td>
                <td>{_format_bytes(a.get('bytes_extracted', 0))}</td>
                <td>{_esc((a.get('started_at') or '')[:19])}</td>
                <td>{_esc((a.get('completed_at') or '')[:19])}</td>
            </tr>"""

        sections_html.append(f"""
        <section class="section">
            <h2>3. Acquisition Methodology</h2>
            <p>Evidence was acquired using Pixtra Mobile Forensics Platform v0.1.0.
               All files were hashed with SHA-256, MD5, and SHA-1 during acquisition.
               A complete chain of custody log was maintained for every action.</p>
            <table class="data-table">
                <thead><tr>
                    <th>Acq. ID</th><th>Method</th><th>Status</th>
                    <th>Files</th><th>Size</th><th>Started</th><th>Completed</th>
                </tr></thead>
                <tbody>{acq_rows}</tbody>
            </table>
        </section>
        """)

    if "evidence_summary" in config.sections:
        ev_rows = ""
        for cat, count in evidence_counts.items():
            ev_rows += f"<tr><td>{_esc(cat.replace('_', ' ').title())}</td><td>{count:,}</td></tr>"

        total = sum(evidence_counts.values())
        sections_html.append(f"""
        <section class="section">
            <h2>4. Evidence Summary</h2>
            <p>Total parsed artifacts: <strong>{total:,}</strong></p>
            <table class="info-table">
                {ev_rows}
            </table>
        </section>
        """)

    if "messages" in config.sections and messages:
        chats = {}
        for m in messages:
            cid = m.get("chat_id") or "unknown"
            chats.setdefault(cid, []).append(m)

        msg_html = ""
        for cid, chat_msgs in list(chats.items())[:20]:
            chat_name = chat_msgs[0].get("chat_name") or cid
            source = chat_msgs[0].get("source", "?")
            msg_html += f'<h4>{_esc(chat_name)} <span class="dim">({source}, {len(chat_msgs)} messages)</span></h4>'
            msg_html += '<div class="chat-container">'
            for m in chat_msgs[:30]:
                cls = "msg-out" if m.get("is_from_me") else "msg-in"
                deleted_tag = ' <span class="deleted">[RECOVERED]</span>' if m.get("is_deleted") else ""
                ts = (m.get("timestamp") or "")[:19]
                text = _esc(m.get("text") or "[No text]")
                sender = _esc(m.get("sender_name") or m.get("sender") or "Me")
                msg_html += f'<div class="msg {cls}"><span class="msg-sender">{sender}</span> <span class="msg-time">{ts}</span><br>{text}{deleted_tag}</div>'
            if len(chat_msgs) > 30:
                msg_html += f'<div class="dim">... and {len(chat_msgs) - 30} more messages</div>'
            msg_html += "</div>"

        sections_html.append(f"""
        <section class="section">
            <h2>5. Messages</h2>
            <p>{len(messages)} messages across {len(chats)} conversations.</p>
            {msg_html}
        </section>
        """)

    if "contacts" in config.sections and contacts:
        ct_rows = ""
        for c in contacts[:100]:
            ct_rows += f"""<tr>
                <td>{_esc(c.get('name'))}</td>
                <td>{_esc(c.get('phone'))}</td>
                <td>{_esc(c.get('email'))}</td>
                <td>{_esc(c.get('organization'))}</td>
            </tr>"""

        sections_html.append(f"""
        <section class="section">
            <h2>6. Contacts</h2>
            <p>{len(contacts)} contacts extracted.</p>
            <table class="data-table">
                <thead><tr><th>Name</th><th>Phone</th><th>Email</th><th>Organization</th></tr></thead>
                <tbody>{ct_rows}</tbody>
            </table>
        </section>
        """)

    if "calls" in config.sections and calls:
        call_rows = ""
        for c in calls[:100]:
            call_rows += f"""<tr>
                <td>{_esc(c.get('number'))}</td>
                <td>{_esc(c.get('name'))}</td>
                <td>{_esc(c.get('direction'))}</td>
                <td>{c.get('duration_seconds', 0)}s</td>
                <td>{_esc((c.get('timestamp') or '')[:19])}</td>
            </tr>"""

        sections_html.append(f"""
        <section class="section">
            <h2>7. Call Log</h2>
            <p>{len(calls)} call records.</p>
            <table class="data-table">
                <thead><tr><th>Number</th><th>Name</th><th>Direction</th><th>Duration</th><th>Time</th></tr></thead>
                <tbody>{call_rows}</tbody>
            </table>
        </section>
        """)

    if "timeline" in config.sections and timeline:
        tl_rows = ""
        for e in timeline[:200]:
            tl_rows += f"""<tr>
                <td>{_esc((e.get('timestamp') or '')[:19])}</td>
                <td>{_esc(e.get('event_type'))}</td>
                <td>{_esc(e.get('title'))}</td>
                <td>{_esc((e.get('description') or '')[:80])}</td>
            </tr>"""

        sections_html.append(f"""
        <section class="section">
            <h2>8. Timeline</h2>
            <p>{len(timeline)} events (showing most recent 200).</p>
            <table class="data-table">
                <thead><tr><th>Time</th><th>Type</th><th>Title</th><th>Description</th></tr></thead>
                <tbody>{tl_rows}</tbody>
            </table>
        </section>
        """)

    if "entity_graph" in config.sections and entities:
        ent_rows = ""
        for e in entities[:50]:
            ent_rows += f"""<tr>
                <td>{_esc(e.get('entity_type'))}</td>
                <td>{_esc(e.get('name'))}</td>
                <td>{_esc(e.get('identifier'))}</td>
                <td>{e.get('occurrence_count', 1)}</td>
                <td>{_esc((e.get('first_seen') or '')[:19])}</td>
                <td>{_esc((e.get('last_seen') or '')[:19])}</td>
            </tr>"""

        sections_html.append(f"""
        <section class="section">
            <h2>9. Entity Graph</h2>
            <p>{len(entities)} entities extracted, {len(entity_edges)} relationships identified.</p>
            <table class="data-table">
                <thead><tr><th>Type</th><th>Name</th><th>Identifier</th><th>Occurrences</th><th>First Seen</th><th>Last Seen</th></tr></thead>
                <tbody>{ent_rows}</tbody>
            </table>
        </section>
        """)

    if "examiner_notes" in config.sections and notes:
        notes_html = ""
        for n in notes:
            inc = "✓ Included in report" if n.get("include_in_report") else ""
            notes_html += f"""
            <div class="note">
                <h4>{_esc(n.get('title'))} <span class="dim">{_esc((n.get('updated_at') or '')[:19])}</span></h4>
                <div class="note-content">{_esc(n.get('content'))}</div>
                <span class="dim">{inc}</span>
            </div>
            """

        sections_html.append(f"""
        <section class="section">
            <h2>10. Examiner Notes</h2>
            {notes_html}
        </section>
        """)

    if "hash_verification" in config.sections:
        hash_rows = ""
        for h in hash_entries[:200]:
            hash_rows += f"""<tr>
                <td><code>{_esc(h.get('file_path', '')[:60])}</code></td>
                <td><code>{_esc((h.get('sha256') or '')[:16])}...</code></td>
                <td>{_format_bytes(h.get('size_bytes', 0))}</td>
            </tr>"""

        sections_html.append(f"""
        <section class="section">
            <h2>11. Hash Verification</h2>
            <p>{len(hash_entries)} files hashed with SHA-256 + MD5 + SHA-1.</p>
            <table class="data-table">
                <thead><tr><th>File</th><th>SHA-256 (truncated)</th><th>Size</th></tr></thead>
                <tbody>{hash_rows}</tbody>
            </table>
        </section>
        """)

    if "chain_of_custody" in config.sections and custody:
        cust_rows = ""
        for c in custody:
            cust_rows += f"""<tr>
                <td>{_esc((c.get('timestamp') or '')[:19])}</td>
                <td>{_esc(c.get('action'))}</td>
                <td>{_esc(c.get('examiner'))}</td>
                <td>{_esc((c.get('details') or '')[:80])}</td>
            </tr>"""

        sections_html.append(f"""
        <section class="section">
            <h2>12. Chain of Custody</h2>
            <p>{len(custody)} logged actions.</p>
            <table class="data-table">
                <thead><tr><th>Timestamp</th><th>Action</th><th>Examiner</th><th>Details</th></tr></thead>
                <tbody>{cust_rows}</tbody>
            </table>
        </section>
        """)

    body = "\n".join(sections_html)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(config.title)} - {_esc(case.get('case_number', ''))}</title>
<style>
{_report_css()}
</style>
</head>
<body>
<header>
    <h1>{_esc(config.title)}</h1>
    <div class="subtitle">
        Case {_esc(case.get('case_number', ''))} - {_esc(case.get('name', ''))}
    </div>
    <div class="meta">
        Examiner: {_esc(config.examiner or case.get('examiner', ''))}
        {f'| Organization: {_esc(config.organization)}' if config.organization else ''}
        | Generated: {generated_at}
    </div>
</header>

<main>
{body}
</main>

<footer>
    <p>Generated by Pixtra Mobile Forensics Platform v0.1.0</p>
    <p>This report was generated automatically from forensically acquired evidence.
       All files were hashed during acquisition for integrity verification.</p>
</footer>
</body>
</html>"""

    return html


def _format_bytes(n) -> str:
    if n is None:
        return "0 B"
    n = int(n)
    if n < 1024:
        return f"{n} B"
    elif n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    elif n < 1024 ** 3:
        return f"{n / (1024**2):.1f} MB"
    else:
        return f"{n / (1024**3):.2f} GB"


def _report_css() -> str:
    return """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        font-size: 11pt;
        line-height: 1.5;
        color: #1C1C1A;
        background: #fff;
        max-width: 900px;
        margin: 0 auto;
        padding: 40px 30px;
    }
    header {
        border-bottom: 2px solid #1B5E3B;
        padding-bottom: 20px;
        margin-bottom: 30px;
    }
    header h1 {
        font-size: 22pt;
        font-weight: 700;
        color: #0D2818;
    }
    header .subtitle {
        font-size: 13pt;
        color: #62625F;
        margin-top: 4px;
    }
    header .meta {
        font-size: 9pt;
        color: #7A7A72;
        margin-top: 8px;
    }
    h2 {
        font-size: 14pt;
        font-weight: 700;
        color: #0D2818;
        border-bottom: 1px solid #E8E8E2;
        padding-bottom: 6px;
        margin-bottom: 12px;
    }
    h4 {
        font-size: 10.5pt;
        font-weight: 600;
        margin: 12px 0 6px;
    }
    .section {
        margin-bottom: 30px;
        page-break-inside: avoid;
    }
    .info-table {
        width: 100%;
        border-collapse: collapse;
        margin: 8px 0;
    }
    .info-table td {
        padding: 5px 10px;
        border-bottom: 1px solid #F0F0EA;
    }
    .info-table .label {
        font-weight: 600;
        width: 200px;
        color: #62625F;
    }
    .data-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 9pt;
        margin: 8px 0;
    }
    .data-table th {
        background: #F6F6F3;
        font-weight: 600;
        text-align: left;
        padding: 6px 8px;
        border-bottom: 2px solid #E8E8E2;
    }
    .data-table td {
        padding: 4px 8px;
        border-bottom: 1px solid #F0F0EA;
        vertical-align: top;
    }
    .data-table tr:hover { background: #FAFAF8; }
    code {
        font-family: 'SF Mono', Menlo, Consolas, monospace;
        font-size: 8.5pt;
        background: #F6F6F3;
        padding: 1px 4px;
        border-radius: 3px;
    }
    .dim { color: #98988F; font-size: 9pt; }
    .notes { color: #62625F; margin-top: 8px; font-style: italic; }
    .chat-container {
        margin: 8px 0 16px;
        padding: 10px;
        background: #FAFAF8;
        border-radius: 8px;
    }
    .msg {
        margin: 4px 0;
        padding: 6px 10px;
        border-radius: 8px;
        font-size: 9.5pt;
        max-width: 75%;
    }
    .msg-in {
        background: #fff;
        border: 1px solid #E8E8E2;
        margin-right: auto;
    }
    .msg-out {
        background: #EDF5EF;
        border: 1px solid #D4EDDF;
        margin-left: auto;
    }
    .msg-sender { font-weight: 600; font-size: 8.5pt; }
    .msg-time { color: #98988F; font-size: 8pt; }
    .deleted { color: #D4382C; font-weight: 600; font-size: 8pt; }
    .note {
        background: #FAFAF8;
        border: 1px solid #E8E8E2;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
    }
    .note-content { margin-top: 6px; white-space: pre-wrap; }
    footer {
        margin-top: 40px;
        padding-top: 16px;
        border-top: 1px solid #E8E8E2;
        font-size: 8.5pt;
        color: #98988F;
    }
    @media print {
        body { padding: 20px; }
        .section { page-break-inside: avoid; }
        header { page-break-after: avoid; }
    }
    """

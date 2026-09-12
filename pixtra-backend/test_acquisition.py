#!/usr/bin/env python3

import json
import os
import sys
import time
import subprocess
import shutil
import requests

BASE_URL = os.environ.get("PIXTRA_API_BASE", "http://127.0.0.1:8080")
TIMEOUT = 30


GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

def ok(msg):     print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg):   print(f"  {RED}✗{RESET} {msg}")
def warn(msg):   print(f"  {YELLOW}⚠{RESET} {msg}")
def info(msg):   print(f"  {CYAN}→{RESET} {msg}")
def header(msg): print(f"\n{BOLD}{msg}{RESET}")
def dim(msg):    print(f"  {DIM}{msg}{RESET}")


def api(method, path, **kwargs):
    url = f"{BASE_URL}{path}"
    try:
        resp = getattr(requests, method)(url, timeout=TIMEOUT, **kwargs)
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text[:500]}
        return resp.status_code, body
    except requests.ConnectionError:
        return None, {"error": "Connection refused - is the backend running on port 8080?"}
    except Exception as e:
        return None, {"error": str(e)}


def check_prerequisites():
    header("STEP 0 - Prerequisites")
    all_ok = True

    status, body = api("get", "/api/health")
    if status == 200:
        ok(f"Backend running (v{body.get('version', '?')})")

        tools = body.get("tools", {})
        for tool_name, tool_info in tools.items():
            if tool_info.get("installed"):
                ver = tool_info.get("version", "")
                ok(f"{tool_name}: installed{f' ({ver})' if ver else ''}")
            else:
                warn(f"{tool_name}: NOT installed")
                if tool_name == "pymobiledevice3":
                    dim(f"  Install: pip3 install pymobiledevice3")
                elif tool_name == "adb":
                    dim(f"  Install: brew install android-platform-tools (Mac) / apt install adb (Linux)")
    else:
        fail("Backend not running!")
        print(f"\n  Start it with:")
        print(f"    cd pixtra-backend")
        print(f"    python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload\n")
        all_ok = False

    v = sys.version_info
    if v >= (3, 9):
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        fail(f"Python {v.major}.{v.minor} - need 3.9+")
        all_ok = False

    return all_ok


def detect_devices():
    header("STEP 1 - Device Detection")

    status, body = api("get", "/api/devices/detect")
    if status != 200:
        fail(f"Detection failed: {body}")
        return None

    if not body:
        warn("No devices detected")
        print()
        print(f"  Troubleshooting:")
        print(f"  • iPhone: Unlock it, tap 'Trust This Computer' when prompted")
        print(f"  • iPhone: Run: python3 -m pymobiledevice3 usbmux list")
        print(f"  • Android: Enable USB Debugging in Developer Options")
        print(f"  • Android: Run: adb devices")
        print(f"  • Make sure the USB cable supports data (not charge-only)")
        return None

    ok(f"Found {len(body)} device(s):")
    for i, dev in enumerate(body):
        platform = dev.get("platform", "?")
        model = dev.get("model_name") or dev.get("model") or "Unknown"
        chip = dev.get("chipset", "?")
        os_ver = dev.get("os_version", "?")
        serial = dev.get("serial", "?")[:16]
        rec = dev.get("recommended_method", "logical_backup")
        caps = dev.get("capabilities", [])

        print(f"\n    [{i}] {BOLD}{model}{RESET}")
        print(f"        Platform:    {platform}")
        print(f"        OS:          {os_ver}")
        print(f"        Chipset:     {chip}")
        print(f"        Serial:      {serial}")
        print(f"        Caps:        {', '.join(caps)}")
        print(f"        Recommended: {rec}")

    return body


def create_case():
    header("STEP 2 - Create Case")

    case_data = {
        "case_number": f"PIXTRA-TEST-{int(time.time()) % 10000:04d}",
        "name": "Acquisition Test",
        "examiner": "Pixtra Tester",
    }

    status, body = api("post", "/api/cases", json=case_data)
    if status == 200:
        case_id = body.get("id")
        ok(f"Case created: {body.get('case_number')} (ID: {case_id})")
        return body
    else:
        fail(f"Case creation failed: {body}")
        return None


def add_device_to_case(case_id, device):
    header("STEP 3 - Add Device to Case")

    status, body = api("post", f"/api/devices/add-to-case?case_id={case_id}", json=device)
    if status == 200:
        device_id = body.get("id")
        ok(f"Device added to case (device ID: {device_id})")
        return body
    else:
        fail(f"Failed to add device: {body}")
        return None


def run_extraction(case_id, device_id, device, method=None):
    header("STEP 4 - Run Extraction")

    platform = device.get("platform", "ios")
    serial = device.get("serial", "")
    udid = device.get("udid", serial)

    if platform == "ios":
        info("Using quick-backup endpoint (pymobiledevice3 backup2)...")
        full = True
        status, body = api("post",
            f"/api/acquisitions/quick-backup?case_id={case_id}&udid={udid}&full={str(full).lower()}")

        if status != 200:
            fail(f"Quick backup failed to start: {body}")

            info("Trying generic /start endpoint as fallback...")
            method = method or "logical_backup"
            acq_data = {
                "case_id": case_id,
                "device_id": device_id,
                "method": method,
            }
            status, body = api("post", "/api/acquisitions/start", json=acq_data)
            if status != 200:
                fail(f"Generic start also failed: {body}")
                return None

    elif platform == "android":
        method = method or device.get("recommended_method", "adb_logical")
        info(f"Starting Android extraction: method={method}")
        acq_data = {
            "case_id": case_id,
            "device_id": device_id,
            "method": method,
        }
        status, body = api("post", "/api/acquisitions/start", json=acq_data)
        if status != 200:
            fail(f"Android extraction failed: {body}")
            return None

    acq_id = body.get("acquisition_id")
    ok(f"Extraction started (ID: {acq_id})")

    info("Monitoring progress (Ctrl+C to skip waiting)...")
    print()

    try:
        last_status = ""
        spin = ["|", "/", "-", "\\"]
        spin_idx = 0
        while True:
            time.sleep(5)
            st, acq = api("get", f"/api/acquisitions/{acq_id}")
            if st != 200:
                warn(f"Could not get status: {acq}")
                continue

            status_str = acq.get("status", "unknown")
            stage = acq.get("stage", "?")
            files = acq.get("files_extracted", 0)
            bytes_val = acq.get("bytes_extracted", 0)
            mb = bytes_val / (1024 * 1024) if bytes_val else 0

            s = spin[spin_idx % len(spin)]
            spin_idx += 1
            line = f"    {s} status={status_str}  stage={stage}  files={files}  size={mb:.1f} MB"
            print(f"\r{line}", end="", flush=True)

            if status_str in ("complete", "failed", "cancelled"):
                print()
                if status_str == "complete":
                    ok(f"Extraction complete: {files} files, {mb:.1f} MB")
                elif status_str == "failed":
                    fail(f"Extraction failed: {acq.get('error_message', 'unknown error')}")
                else:
                    warn("Extraction cancelled")
                return acq

    except KeyboardInterrupt:
        print()
        warn("Skipped waiting - extraction may still be running in the background")
        st, acq = api("get", f"/api/acquisitions/{acq_id}")
        return acq if st == 200 else body


def parse_extraction(acq_id, case_id):
    header("STEP 5 - Parse Extracted Data")

    st, acq = api("get", f"/api/acquisitions/{acq_id}")
    if st == 200 and acq.get("status") != "complete":
        warn(f"Extraction status: {acq.get('status')} - waiting...")
        for _ in range(60):
            time.sleep(5)
            st, acq = api("get", f"/api/acquisitions/{acq_id}")
            if st == 200 and acq.get("status") == "complete":
                break
        else:
            fail("Extraction didn't complete in 5 minutes")
            return None

    info("Running parser engine...")
    status, body = api("post", f"/api/analysis/parse/{acq_id}")

    if status == 200:
        parsed = body.get("parsed", {})
        ok(f"Parse results:")
        total = 0
        for key, count in parsed.items():
            if isinstance(count, int):
                label = "✓" if count > 0 else " - "
                print(f"        {label} {key}: {count}")
                total += count
            elif key == "format":
                dim(f"      Format: {count}")
            elif key == "domains_found":
                dim(f"      iTunes domains: {count}")

        if total == 0:
            warn("No artifacts parsed - this may mean:")
            print(f"        • Logical backup doesn't include this data (needs encrypted backup for WhatsApp)")
            print(f"        • Parser couldn't find known databases in the extraction")
            print(f"        • Try encrypted backup: set a backup password on the iPhone first")

        return parsed
    else:
        fail(f"Parser failed: {body}")
        return None


def build_entity_graph(case_id):
    header("STEP 6 - Build Entity Graph")

    status, body = api("post", f"/api/analysis/entities/{case_id}")
    if status == 200:
        graph = body.get("graph", {})
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        people = body.get("people", 0)
        locations = body.get("locations", 0)
        apps = body.get("apps", 0)

        ok(f"Entity graph built:")
        print(f"        People:    {people}")
        print(f"        Locations: {locations}")
        print(f"        Apps:      {apps}")
        print(f"        Nodes:     {len(nodes)}")
        print(f"        Edges:     {len(edges)}")

        if nodes:
            dim(f"      Top entities:")
            for n in sorted(nodes, key=lambda x: x.get("occurrences", 0), reverse=True)[:5]:
                print(f"          {n['type']:10s} {n['name'][:30]:30s}  (×{n.get('occurrences', 1)})")
        return body
    else:
        fail(f"Entity extraction failed: {body}")
        return None


def query_evidence(case_id):
    header("STEP 7 - Query Evidence")

    st, cats = api("get", f"/api/analysis/evidence/{case_id}")
    if st == 200:
        ok(f"Evidence categories (total: {cats.get('total_artifacts', 0)}):")
        for cat, count in cats.get("categories", {}).items():
            label = "✓" if count > 0 else " - "
            print(f"        {label} {cat}: {count}")

        msg_sources = cats.get("message_sources", {})
        if msg_sources:
            dim(f"      Message sources:")
            for src, count in msg_sources.items():
                print(f"          {src}: {count}")
    else:
        warn(f"Evidence query failed: {cats}")

    st, chats = api("get", f"/api/analysis/evidence/{case_id}/chats")
    if st == 200 and chats:
        ok(f"Chat threads: {len(chats)}")
        for c in chats[:5]:
            name = c.get("chat_name", "?")[:30]
            src = c.get("source", "?")
            count = c.get("message_count", 0)
            print(f"        {src:12s} {name:30s}  ({count} messages)")

    st, timeline = api("get", f"/api/analysis/timeline/{case_id}")
    if st == 200:
        events = timeline.get("events", [])
        total_events = timeline.get("total_events", 0)
        ok(f"Timeline: {total_events} total events")
        if events:
            dim(f"      Recent events:")
            for e in events[:5]:
                ts = (e.get("timestamp") or "?")[:19]
                etype = e.get("event_type", "?")
                title = e.get("title", "?")[:40]
                print(f"          {ts}  {etype:10s}  {title}")

    st, contacts = api("get", f"/api/analysis/evidence/{case_id}/contacts")
    if st == 200 and contacts:
        ok(f"Contacts: {len(contacts)}")
        for c in contacts[:5]:
            name = c.get("name", "?")[:25]
            phone = c.get("phone", " - ")
            print(f"        {name:25s}  {phone}")


def verify_hashes(acq_id):
    header("STEP 8 - Hash Verification")

    st, hashes = api("get", f"/api/acquisitions/{acq_id}/hashes")
    if st == 200 and hashes:
        ok(f"Hash manifest: {len(hashes)} files hashed")
    else:
        info("No hash manifest in DB - generating now via verify endpoint...")

    st, result = api("post", f"/api/acquisitions/{acq_id}/verify")
    if st == 200:
        if result.get("verified"):
            ok(f"All {result.get('total_files', 0)} files verified - integrity intact ✓")
        else:
            mismatches = result.get("mismatches", 0)
            fail(f"Verification: {mismatches} mismatches out of {result.get('total_files', 0)} files")
            for m in result.get("mismatch_details", [])[:5]:
                print(f"        {m['file_path']}")
    elif st == 400:
        warn(f"Verification skipped: {result.get('detail', 'no manifest')}")
    else:
        fail(f"Verification failed: {result}")


def check_custody(case_id):
    header("STEP 9 - Chain of Custody")

    st, log = api("get", f"/api/cases/{case_id}/custody")
    if st == 200 and log:
        ok(f"Custody log: {len(log)} entries")
        for entry in log:
            ts = (entry.get("timestamp") or "?")[:19]
            action = entry.get("action", "?")
            details = (entry.get("details") or "")[:60]
            print(f"        {ts}  {action:25s}  {details}")
    else:
        warn("No custody log entries")


def list_files(case_id):
    header("STEP 10 - Extraction Files")

    st, result = api("get", f"/api/analysis/files/{case_id}")
    if st == 200:
        files = result.get("files", [])
        total = result.get("total", 0)
        ok(f"Files on disk: {total}")

        by_type = {}
        for f in files:
            ft = f.get("type", "other")
            by_type.setdefault(ft, []).append(f)

        for ft, flist in sorted(by_type.items()):
            total_size = sum(f.get("size_bytes", 0) for f in flist)
            mb = total_size / (1024 * 1024)
            print(f"        {ft:12s}: {len(flist):4d} files ({mb:.1f} MB)")

        if not files:
            warn("No files found - extraction may still be in progress")
    else:
        warn(f"File listing failed: {result}")


def generate_report_test(case_id):
    header("STEP 11 - Generate Report")

    report_data = {
        "title": "Forensic Examination Report",
        "format": "html",
        "sections": [
            "case_summary", "device_info", "methodology",
            "evidence_summary", "messages", "contacts", "calls",
            "timeline", "entity_graph", "hash_verification",
            "chain_of_custody",
        ],
    }

    status, body = api("post", f"/api/reports/{case_id}/generate", json=report_data)
    if status == 200:
        fmt = body.get("format", "?")
        path = body.get("output_path", "?")
        gen_time = body.get("generation_time_ms", 0)
        ok(f"Report generated ({fmt}) in {gen_time}ms")
        dim(f"      Path: {path}")

        st, rlist = api("get", f"/api/reports/{case_id}/list")
        if st == 200:
            reports = rlist.get("reports", [])
            if reports:
                for r in reports:
                    print(f"        {r['filename']}  ({r['format']}, {r.get('size_bytes', 0)} bytes)")
                    print(f"        Download: {BASE_URL}{r['download_url']}")
    else:
        fail(f"Report generation failed: {body}")


def main():
    print()
    print(f"{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  PIXTRA - Acquisition Test Harness{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}")

    if not check_prerequisites():
        print(f"\n{RED}Fix prerequisites above before continuing.{RESET}\n")
        sys.exit(1)

    devices = detect_devices()
    if not devices:
        print(f"\n{YELLOW}Plug in a device and run again.{RESET}\n")
        sys.exit(1)

    if len(devices) > 1:
        print()
        choice = input(f"  Select device [0-{len(devices)-1}]: ").strip()
        try:
            idx = int(choice)
            device = devices[idx]
        except (ValueError, IndexError):
            device = devices[0]
    else:
        device = devices[0]

    case = create_case()
    if not case:
        sys.exit(1)
    case_id = case["id"]

    case_device = add_device_to_case(case_id, device)
    if not case_device:
        sys.exit(1)
    device_id = case_device["id"]

    acq = run_extraction(case_id, device_id, device)
    if not acq:
        sys.exit(1)
    acq_id = acq.get("acquisition_id") or acq.get("id")

    if acq.get("status") not in ("complete", "failed", "cancelled"):
        info("Extraction still running - waiting for completion...")
        for _ in range(360):
            time.sleep(5)
            st, acq = api("get", f"/api/acquisitions/{acq_id}")
            if st == 200:
                status = acq.get("status")
                files = acq.get("files_extracted", 0)
                mb = acq.get("bytes_extracted", 0) / (1024 * 1024)
                print(f"\r    ... {status} - {files} files, {mb:.1f} MB   ", end="", flush=True)
                if status in ("complete", "failed", "cancelled"):
                    print()
                    break
        else:
            warn("Timed out waiting for extraction")

    if acq.get("status") == "failed":
        fail(f"Extraction failed: {acq.get('error_message', 'unknown')}")
        print(f"\n  Troubleshooting:")
        print(f"  • iPhone: Make sure you tapped 'Trust This Computer'")
        print(f"  • iPhone: Try setting a backup password first, then retry")
        print(f"  • Android: Make sure USB debugging is enabled")
        print(f"  • Check backend logs for details")
        sys.exit(1)

    parsed = parse_extraction(acq_id, case_id)

    if parsed:
        build_entity_graph(case_id)

    query_evidence(case_id)

    verify_hashes(acq_id)

    check_custody(case_id)

    list_files(case_id)

    generate_report_test(case_id)

    header("SUMMARY")
    print(f"""
    Case ID:        {case_id}
    Device ID:      {device_id}
    Acquisition ID: {acq_id}
    Status:         {acq.get('status', 'unknown')}
    Files:          {acq.get('files_extracted', 0)}
    Size:           {(acq.get('bytes_extracted', 0) / (1024**2)):.1f} MB

    API endpoints to explore:
      GET  {BASE_URL}/api/cases/{case_id}
      GET  {BASE_URL}/api/cases/{case_id}/custody
      GET  {BASE_URL}/api/devices/case/{case_id}
      GET  {BASE_URL}/api/acquisitions/{acq_id}
      GET  {BASE_URL}/api/analysis/evidence/{case_id}
      GET  {BASE_URL}/api/analysis/evidence/{case_id}/chats
      GET  {BASE_URL}/api/analysis/evidence/{case_id}/messages?source=imessage
      GET  {BASE_URL}/api/analysis/evidence/{case_id}/contacts
      GET  {BASE_URL}/api/analysis/evidence/{case_id}/calls
      GET  {BASE_URL}/api/analysis/timeline/{case_id}
      GET  {BASE_URL}/api/analysis/graph/{case_id}
      GET  {BASE_URL}/api/analysis/files/{case_id}
      POST {BASE_URL}/api/reports/{case_id}/generate
      GET  {BASE_URL}/api/reports/{case_id}/list
    """)

    print(f"{GREEN}{BOLD}Done.{RESET}\n")


if __name__ == "__main__":
    main()

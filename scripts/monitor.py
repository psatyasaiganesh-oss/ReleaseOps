#!/usr/bin/env python3
"""External readiness observer. Spool failed checks and upload after recovery."""
import argparse
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:8080")
parser.add_argument("--token-file", type=Path, default=Path(".local/dev-token"))
parser.add_argument("--spool", type=Path, default=Path(".local/monitor-spool.json"))
parser.add_argument("--interval", type=float, default=15)
parser.add_argument("--once", action="store_true")
args = parser.parse_args()
if args.interval < 1:
    raise SystemExit("Use a monitoring interval of at least one second")
token = os.environ.get("API_TOKEN") or args.token_file.read_text().strip()
args.spool.parent.mkdir(parents=True, exist_ok=True)
queue = json.loads(args.spool.read_text()) if args.spool.exists() else []
if not isinstance(queue, list):
    raise SystemExit("Invalid monitor spool; preserve it and choose a new --spool path")
base = args.url.rstrip("/")
while True:
    started = time.monotonic()
    item = {"id": str(uuid.uuid4()), "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "ok": False, "latency_ms": 0, "error": ""}
    try:
        with urllib.request.urlopen(base + "/readyz", timeout=3) as response:
            item["ok"] = response.status == 200 and json.load(response)["status"] == "ready"
    except urllib.error.HTTPError as exc:
        item["error"] = f"HTTP {exc.code}"
    except (OSError, ValueError, KeyError):
        item["error"] = "Readiness endpoint unreachable or invalid"
    item["latency_ms"] = round((time.monotonic() - started) * 1000, 2)
    queue.append(item)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=47)).isoformat(timespec="seconds")
    queue = [entry for entry in queue if entry["observed_at"] >= cutoff][-10000:]
    upload_error = ""
    request = urllib.request.Request(base + "/api/probes", method="POST",
        data=json.dumps({"observations": queue[:200]}).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            if response.status == 201:
                queue = queue[200:]
    except urllib.error.HTTPError as exc:
        upload_error = f"HTTP {exc.code}"
    except OSError:
        upload_error = "Observer upload unavailable"
    temporary = args.spool.with_suffix(".tmp")
    temporary.write_text(json.dumps(queue))
    temporary.chmod(0o600)
    temporary.replace(args.spool)
    print(json.dumps({"ready": item["ok"], "latency_ms": item["latency_ms"], "queued": len(queue), "upload_error": upload_error}), flush=True)
    if args.once:
        break
    try:
        time.sleep(max(0, args.interval - (time.monotonic() - started)))
    except KeyboardInterrupt:
        break

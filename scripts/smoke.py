#!/usr/bin/env python3
"""Read-only deployment checks; safe to run without creating workspace records."""
import argparse
import json
import os
import time
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:8080")
parser.add_argument("--attempts", type=int, default=20)
args = parser.parse_args()
base = args.url.rstrip("/")
for attempt in range(args.attempts):
    try:
        with urllib.request.urlopen(base + "/readyz", timeout=2) as response:
            readiness = json.load(response)
        if readiness["status"] != "ready":
            raise ValueError("Service is not ready")
        break
    except (OSError, ValueError):
        if attempt == args.attempts - 1:
            raise SystemExit("Readiness check failed")
        time.sleep(0.25)
if os.environ.get("EXPECTED_VERSION") and readiness["version"] != os.environ["EXPECTED_VERSION"]:
    raise SystemExit("Version mismatch")
with urllib.request.urlopen(base + "/api/state", timeout=2) as response:
    state = json.load(response)
if state["version"] != readiness["version"] or "tasks" not in state:
    raise SystemExit("Application API contract failed")
with urllib.request.urlopen(base + "/", timeout=2) as response:
    if b"ReleaseOps" not in response.read() or not response.headers.get("Content-Security-Policy"):
        raise SystemExit("Dashboard or response header check failed")
with urllib.request.urlopen(base + "/metrics", timeout=2) as response:
    if b"releaseops_build_info" not in response.read():
        raise SystemExit("Metrics endpoint check failed")
print(json.dumps({"result": "passed", "checks": ["readiness", "version", "API", "dashboard", "metrics"], "environment": readiness["environment"], "version": readiness["version"]}))

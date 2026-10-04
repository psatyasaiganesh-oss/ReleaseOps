#!/usr/bin/env python3
"""Record a release only after the app reports ready; no secrets in arguments."""
import json
import os
import sys
import urllib.request

base = sys.argv[1].rstrip("/")
with urllib.request.urlopen(base + "/readyz", timeout=5) as response:
    ready = json.load(response)
expected = os.environ.get("EXPECTED_VERSION")
if ready["status"] != "ready" or ready["environment"] != os.environ["APP_ENV"]:
    raise SystemExit("Application readiness or environment mismatch")
if expected and ready["version"] != expected:
    raise SystemExit("Application version does not match the expected commit")
request = urllib.request.Request(base + "/api/releases", method="POST", data=json.dumps({
    "version": ready["version"], "environment": ready["environment"],
    "image": os.environ["RELEASE_IMAGE_REF"], "action": os.environ.get("RELEASE_ACTION", "deploy")}).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ["API_TOKEN"]})
with urllib.request.urlopen(request, timeout=5) as response:
    if response.status != 201:
        raise SystemExit("Release registration failed")

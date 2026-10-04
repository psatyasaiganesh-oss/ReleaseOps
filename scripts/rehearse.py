#!/usr/bin/env python3
"""Exercise real local application processes; this is not a Docker/cloud test."""
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
token = secrets.token_urlsafe(32)
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
base = f"http://127.0.0.1:{port}"

def request(path, data=None):
    request = urllib.request.Request(base + path, data=json.dumps(data).encode() if data else None,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token})
    with urllib.request.urlopen(request, timeout=2) as response:
        return json.load(response)

with tempfile.TemporaryDirectory(prefix="releaseops-rehearsal-") as temporary:
    folder = Path(temporary)
    marker = folder / "unhealthy"
    env = dict(os.environ, API_TOKEN=token, APP_ENV="staging", DATABASE_PATH=str(folder / "app.db"), FAILURE_FILE=str(marker))
    log = (folder / "server.log").open("w")
    process = None
    def stop():
        global process
        if process:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process = None

    def start(version, ready=True):
        global process
        process = subprocess.Popen([sys.executable, "-m", "releaseops.server", "--port", str(port)],
                                   cwd=root, env=dict(env, APP_VERSION=version), stdout=log, stderr=log)
        for _ in range(40):
            try:
                response = request("/readyz")
                if ready and response["status"] == "ready":
                    return
            except urllib.error.HTTPError as error:
                if not ready and error.code == 503:
                    return
            except OSError:
                pass
            if process.poll() is not None:
                raise RuntimeError("Application process exited unexpectedly")
            time.sleep(0.1)
        raise RuntimeError("Readiness result did not match the release gate")

    def record(version, action="local-rehearsal"):
        request("/api/releases", {"version": version, "environment": "staging", "image": "local-process:" + version, "action": action})

    def observe():
        subprocess.run([sys.executable, str(root / "scripts/monitor.py"), "--url", base,
                        "--spool", str(folder / "spool.json"), "--once"], env=env, check=True, capture_output=True)
    try:
        start("rehearsal-v1")
        task = request("/api/tasks", {"title": "Data must survive a release", "owner": "Rehearsal"})
        record("rehearsal-v1")
        observe()
        stop()
        observe()  # Persist an unreachable observation while the app is stopped.
        start("rehearsal-v2")
        record("rehearsal-v2")
        observe()
        assert request("/api/state")["tasks"][0]["id"] == task["id"]
        stop()
        marker.touch()
        start("rehearsal-broken", ready=False)
        observe()
        # Failed candidate must not be recorded as a successful release.
        assert len(request("/api/state")["releases"]) == 2
        stop()
        marker.unlink()
        start("rehearsal-v2")
        record("rehearsal-v2", "rollback")
        observe()
        state = request("/api/state")
        assert state["version"] == "rehearsal-v2" and state["tasks"][0]["id"] == task["id"]
        assert state["observation"]["count"] == 5 and state["observation"]["passed"] == 3
        assert state["releases"][0]["action"] == "rollback"
        print(json.dumps({"result": "passed", "checks": ["v1 start", "v2 release", "failed readiness gate", "rollback to v2", "data preserved", "downtime observations replayed"], "sampled_pass_rate": state["observation"]["success_percent"], "scope": "local Python processes, not Docker or AWS"}, indent=2))
    finally:
        stop()
        log.close()

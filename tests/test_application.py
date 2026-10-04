import concurrent.futures
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from releaseops.db import InvalidInput, Store, now
from releaseops.server import Application, make_server

TOKEN = "test-only-operator-token-0123456789"
ROOT = Path(__file__).resolve().parents[1]


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "app.db"
        self.marker = Path(self.temp.name) / "unhealthy"
        self.store = Store(self.database)
        app = Application(self.store, TOKEN, "staging", "test-v1", str(self.marker))
        self.server = make_server(app, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, method="GET", data=None, token=TOKEN, headers=None, raw=None):
        request_headers = {"Authorization": "Bearer " + token}
        if data is not None or raw is not None:
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})
        payload = raw if raw is not None else json.dumps(data).encode() if data is not None else None
        request = urllib.request.Request(self.base + path, method=method, data=payload, headers=request_headers)
        try:
            response = urllib.request.urlopen(request, timeout=4)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            content = response.read()
            if response.headers.get_content_type() == "application/json":
                content = json.loads(content)
            return response.status, content, response.headers

    def test_empty_workspace_has_no_fabricated_availability_or_releases(self):
        status, state, _ = self.request("/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(state["releases"], [])
        self.assertIsNone(state["observation"]["success_percent"])

    def test_token_required_and_validated(self):
        self.assertEqual(self.request("/api/tasks", "POST", {"title": "Unauthorized"}, token="wrong")[0], 401)
        self.assertEqual(self.request("/api/access", token="wrong")[0], 401)
        self.assertEqual(self.request("/api/access")[0], 200)
        self.assertEqual(self.store.state()["tasks"], [])

    def test_task_lifecycle_persists_after_reopening_database(self):
        status, task, _ = self.request("/api/tasks", "POST", {"title": "Test rollout", "owner": "Platform"})
        self.assertEqual(status, 201)
        self.assertEqual(self.request(f'/api/tasks/{task["id"]}', "PATCH", {"status": "done"})[0], 200)
        self.assertEqual(Store(self.database).state()["tasks"][0]["status"], "done")

    def test_incident_resolution_is_recorded_and_cannot_be_reopened(self):
        _, item, _ = self.request("/api/incidents", "POST", {"title": "Build failed", "severity": "SEV2"})
        path = f'/api/incidents/{item["id"]}'
        self.assertEqual(self.request(path, "PATCH", {"status": "investigating"})[0], 200)
        _, resolved, _ = self.request(path, "PATCH", {"status": "resolved"})
        self.assertIsNotNone(resolved["resolved_at"])
        self.assertEqual(self.request(path, "PATCH", {"status": "open"})[0], 400)

    def test_invalid_status_and_missing_item(self):
        self.assertEqual(self.request("/api/tasks", "POST", {"title": "Task", "status": "unexpected"})[0], 400)
        self.assertEqual(self.request("/api/tasks/123", "PATCH", {"status": "done"})[0], 404)

    def test_invalid_json_body_and_size_are_rejected(self):
        self.assertEqual(self.request("/api/tasks", "POST", raw=b'not-json')[0], 400)
        self.assertEqual(self.request("/api/tasks", "POST", raw=b'[]')[0], 400)
        self.assertEqual(self.request("/api/tasks", "POST", raw=b'{"title":NaN}')[0], 400)
        self.assertEqual(self.request("/api/tasks", "POST", raw=b'x' * 131073)[0], 400)

    def test_cross_origin_writes_are_blocked(self):
        self.assertEqual(self.request("/api/tasks", "POST", {"title": "Task"}, headers={"Origin": "https://other.example"})[0], 403)

    def test_health_is_distinct_from_readiness(self):
        self.marker.touch()
        self.assertEqual(self.request("/healthz")[0], 200)
        self.assertEqual(self.request("/readyz")[0], 503)
        self.marker.unlink()
        self.assertEqual(self.request("/readyz")[0], 200)

    def test_probe_ingestion_is_deduplicated_and_calculates_real_success_rate(self):
        checks = [{"id": "check1", "observed_at": now(), "ok": True, "latency_ms": 10},
                  {"id": "check2", "observed_at": now(), "ok": False, "latency_ms": 20, "error": "HTTP 503"}]
        self.assertEqual(self.request("/api/probes", "POST", {"observations": checks})[0], 201)
        self.request("/api/probes", "POST", {"observations": checks})
        observation = self.store.state()["observation"]
        self.assertEqual(observation["count"], 2)
        self.assertEqual(observation["success_percent"], 50)
        self.assertEqual(observation["latency_ms"], 10)

    def test_probe_batch_is_atomic_when_an_item_is_invalid(self):
        good = {"id": "valid", "observed_at": now(), "ok": True, "latency_ms": 1}
        bad = {**good, "id": "bad", "ok": "yes"}
        self.assertEqual(self.request("/api/probes", "POST", {"observations": [good, bad]})[0], 400)
        self.assertEqual(self.store.state()["observation"]["count"], 0)

    def test_release_environment_must_match_application(self):
        data = {"version": "v1", "image": "releaseops:v1", "environment": "production"}
        self.assertEqual(self.request("/api/releases", "POST", data)[0], 400)
        data["environment"] = "staging"
        self.assertEqual(self.request("/api/releases", "POST", data)[0], 201)

    def test_static_allowlist_and_response_headers(self):
        self.assertEqual(self.request("/../server.py")[0], 404)
        self.assertEqual(self.request("/.local/dev-token")[0], 404)
        status, body, headers = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"ReleaseOps", body)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_metrics_are_real_and_do_not_leak_operator_token(self):
        self.request("/readyz")
        status, body, _ = self.request("/metrics")
        self.assertEqual(status, 200)
        self.assertIn(b'releaseops_http_requests_total{route="/readyz"', body)
        self.assertNotIn(TOKEN.encode(), body)

    def test_parallel_task_writes_do_not_lose_data(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda number: self.request("/api/tasks", "POST", {"title": f"Task {number}"})[0], range(12)))
        self.assertEqual(results, [201] * 12)
        self.assertEqual(len(self.store.state()["tasks"]), 12)

    def test_backup_includes_committed_wal_data(self):
        self.store.create("tasks", {"title": "Preserve this task"})
        backup = Path(self.temp.name) / "backup.db"
        result = subprocess.run([sys.executable, str(ROOT / "scripts/backup.py"), str(self.database), str(backup)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        with sqlite3.connect(backup) as database:
            self.assertEqual(database.execute("SELECT title FROM tasks").fetchone()[0], "Preserve this task")

    def test_demo_seed_does_not_create_release_or_probe_evidence(self):
        self.store.seed_demo()
        state = self.store.state()
        self.assertTrue(state["demo"])
        self.assertEqual(state["releases"], [])
        self.assertEqual(state["observation"]["count"], 0)


if __name__ == "__main__":
    unittest.main()

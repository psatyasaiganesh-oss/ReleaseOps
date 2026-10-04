"""Dependency-free HTTP server for this private DevOps learning lab."""
import argparse
import hmac
import json
import logging
import mimetypes
import os
import re
import sqlite3
import threading
import time
import uuid
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from releaseops.db import InvalidInput, NotFound, Store

LOGGER = logging.getLogger("releaseops")
STATIC = Path(__file__).parent / "static"
MAX_BODY = 128 * 1024


class Application:
    def __init__(self, store, token, environment="development", version="1.0.0", failure_file=""):
        if len(token) < 24:
            raise ValueError("API_TOKEN must contain at least 24 characters; use scripts/dev.py for local setup")
        if environment not in ("development", "staging", "production", "ci"):
            raise ValueError("APP_ENV must be development, staging, production, or ci")
        self.store, self.token = store, token
        self.environment, self.version = environment, version
        self.failure_file = failure_file
        self.started = time.monotonic()
        self.lock = threading.Lock()
        self.requests = Counter()
        self.duration = Counter()
        self.samples = Counter()

    def readiness(self):
        ready = not (self.failure_file and Path(self.failure_file).exists())
        try:
            ready = ready and self.store.healthy()
        except sqlite3.Error:
            ready = False
        return {"status": "ready" if ready else "unavailable", "environment": self.environment,
                "version": self.version, "uptime_seconds": round(time.monotonic() - self.started, 1)}

    def observe(self, route, method, status, elapsed):
        with self.lock:
            self.requests[(route, method, str(status))] += 1
            self.duration[route] += elapsed
            self.samples[route] += 1

    def metrics(self):
        state = self.store.state()
        def quote(value):
            return json.dumps(str(value))
        lines = ["# TYPE releaseops_http_requests_total counter"]
        with self.lock:
            for (route, method, status), count in sorted(self.requests.items()):
                lines.append(f'releaseops_http_requests_total{{route={quote(route)},method={quote(method)},status={quote(status)}}} {count}')
            lines.append("# TYPE releaseops_http_request_duration_seconds summary")
            for route, total in sorted(self.duration.items()):
                lines.append(f'releaseops_http_request_duration_seconds_sum{{route={quote(route)}}} {total:.6f}')
                lines.append(f'releaseops_http_request_duration_seconds_count{{route={quote(route)}}} {self.samples[route]}')
        lines += ["# TYPE releaseops_incidents_open gauge",
                  f'releaseops_incidents_open {state["counts"]["open_incidents"]}',
                  "# TYPE releaseops_probe_observations gauge",
                  f'releaseops_probe_observations {state["observation"]["count"]}',
                  "# TYPE releaseops_build_info gauge",
                  f'releaseops_build_info{{version={quote(self.version)},environment={quote(self.environment)}}} 1']
        if state["observation"]["success_percent"] is not None:
            lines += ["# TYPE releaseops_probe_success_ratio gauge",
                      f'releaseops_probe_success_ratio {state["observation"]["success_percent"] / 100:.6f}']
        return "\n".join(lines) + "\n"


def make_server(app, host="127.0.0.1", port=8080):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ReleaseOps"
        sys_version = ""

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, *args):
            # Request bodies, authorization headers and query strings are never logged.
            pass

        def send(self, status, body, content_type="application/json; charset=utf-8"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, allow_nan=False).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.response_status = status
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Request-ID", self.request_id)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def body(self):
            if self.headers.get("Transfer-Encoding"):
                raise InvalidInput("Chunked request bodies are unsupported")
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1:
                raise InvalidInput("Provide one Content-Length header")
            try:
                length = int(lengths[0])
            except ValueError as exc:
                raise InvalidInput("Invalid Content-Length") from exc
            if not 0 < length <= MAX_BODY:
                raise InvalidInput("Request body must contain 1–131072 bytes")
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise InvalidInput("Content-Type must be application/json")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise InvalidInput("Incomplete request body")
            try:
                data = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            except (ValueError, UnicodeError) as exc:
                raise InvalidInput("Request body must be valid JSON") from exc
            if not isinstance(data, dict):
                raise InvalidInput("Request body must be a JSON object")
            return data

        def handle_request(self):
            self.request_id = str(uuid.uuid4())
            self.response_status = 500
            start = time.monotonic()
            path = urlsplit(self.path).path
            route = re.sub(r"/\d+$", "/:id", path)
            # Bound metric cardinality: arbitrary URLs never become labels.
            known = ("/", "/index.html", "/app.js", "/styles.css", "/healthz", "/readyz", "/metrics", "/api/state",
                     "/api/access", "/api/tasks", "/api/incidents", "/api/releases", "/api/probes", "/api/tasks/:id", "/api/incidents/:id")
            route = route if route in known else "unmatched"
            try:
                if self.command in ("GET", "HEAD"):
                    if path == "/healthz":
                        self.send(200, {"status": "alive"})
                    elif path == "/readyz":
                        readiness = app.readiness()
                        self.send(200 if readiness["status"] == "ready" else 503, readiness)
                    elif path == "/api/access":
                        valid = hmac.compare_digest(self.headers.get("Authorization", "").encode(), ("Bearer " + app.token).encode())
                        self.send(200 if valid else 401, {"authorized": valid})
                    elif path == "/api/state":
                        data = app.store.state()
                        data.update(environment=app.environment, version=app.version, health=app.readiness())
                        self.send(200, data)
                    elif path == "/metrics":
                        self.send(200, app.metrics(), "text/plain; version=0.0.4; charset=utf-8")
                    elif path in ("/", "/index.html", "/styles.css", "/app.js"):
                        name = "index.html" if path == "/" else path.lstrip("/")
                        kind = mimetypes.guess_type(name)[0] or "application/octet-stream"
                        self.send(200, (STATIC / name).read_bytes(), kind + "; charset=utf-8")
                    else:
                        self.send(404, {"error": "Not found", "request_id": self.request_id})
                    return
                if self.command not in ("POST", "PATCH"):
                    self.send(405, {"error": "Method not allowed"})
                    return
                origin = self.headers.get("Origin")
                if origin and (urlsplit(origin).netloc != self.headers.get("Host") or urlsplit(origin).scheme not in ("http", "https")):
                    self.send(403, {"error": "Cross-origin writes are forbidden"})
                    return
                authorization = self.headers.get("Authorization", "")
                if not hmac.compare_digest(authorization.encode(), ("Bearer " + app.token).encode()):
                    self.send(401, {"error": "Enter a valid operator token to make changes"})
                    return
                data = self.body()
                if self.command == "POST" and path == "/api/probes":
                    self.send(201, app.store.probes(data))
                elif self.command == "POST" and path in ("/api/tasks", "/api/incidents", "/api/releases"):
                    self.send(201, app.store.create(path.split("/")[-1], data, app.environment))
                else:
                    match = re.fullmatch(r"/api/(tasks|incidents)/(\d+)", path)
                    if self.command == "PATCH" and match:
                        self.send(200, app.store.update(match[1], int(match[2]), data))
                    else:
                        self.send(404, {"error": "Not found"})
            except InvalidInput as exc:
                self.send(400, {"error": str(exc), "request_id": self.request_id})
            except NotFound as exc:
                self.send(404, {"error": str(exc), "request_id": self.request_id})
            except sqlite3.Error:
                self.send(503, {"error": "Database unavailable", "request_id": self.request_id})
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                self.close_connection = True
            except Exception:
                LOGGER.exception("Unexpected failure", extra={"request_id": self.request_id})
                self.send(500, {"error": "Internal server error", "request_id": self.request_id})
            finally:
                elapsed = time.monotonic() - start
                app.observe(route, self.command, self.response_status, elapsed)
                LOGGER.info(json.dumps({"request_id": self.request_id, "method": self.command, "route": route,
                                        "status": self.response_status, "duration_ms": round(elapsed * 1000, 2)}))

        do_GET = handle_request
        do_HEAD = handle_request
        do_POST = handle_request
        do_PATCH = handle_request
        do_DELETE = handle_request

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description="Run the ReleaseOps learning lab")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    parser.add_argument("--demo", action="store_true", help="Seed explicitly labeled example tickets")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    store = Store(os.environ.get("DATABASE_PATH", ".local/releaseops.db"))
    if args.demo:
        store.seed_demo()
    app = Application(store, os.environ.get("API_TOKEN", ""), os.environ.get("APP_ENV", "development"),
                      os.environ.get("APP_VERSION", "1.0.0"), os.environ.get("FAILURE_FILE", ""))
    server = make_server(app, args.host, args.port)
    LOGGER.info(json.dumps({"event": "server_started", "environment": app.environment, "version": app.version, "port": args.port}))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

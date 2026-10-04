"""SQLite persistence. Each request uses a separate connection and transaction."""
import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


class InvalidInput(ValueError):
    pass


class NotFound(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def text(data, key, maximum=160, default=None):
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise InvalidInput(f"{key} must contain 1–{maximum} characters")
    return value.strip()


def choice(data, key, options, default=None):
    value = data.get(key, default)
    if value not in options:
        raise InvalidInput(f"{key} must be one of: {', '.join(options)}")
    return value


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY, title TEXT NOT NULL, owner TEXT NOT NULL,
                    status TEXT NOT NULL, priority TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, demo INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS incidents (
                    id INTEGER PRIMARY KEY, title TEXT NOT NULL, service TEXT NOT NULL,
                    severity TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, resolved_at TEXT, demo INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS releases (
                    id INTEGER PRIMARY KEY, version TEXT NOT NULL, image TEXT NOT NULL,
                    environment TEXT NOT NULL, action TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS probes (
                    id TEXT PRIMARY KEY, observed_at TEXT NOT NULL, ok INTEGER NOT NULL,
                    latency_ms REAL NOT NULL, error TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS probes_time ON probes(observed_at);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL
                );
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def event(db, kind, message):
        db.execute("INSERT INTO events(kind,message,created_at) VALUES(?,?,?)", (kind, message, now()))

    def healthy(self):
        with self.connect() as db:
            return db.execute("SELECT 1").fetchone()[0] == 1

    def create(self, resource, data, environment="development"):
        stamp = now()
        with self.connect() as db:
            title = text(data, "title") if resource != "releases" else ""
            if resource == "tasks":
                cursor = db.execute(
                    "INSERT INTO tasks(title,owner,status,priority,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    (title, text(data, "owner", 60, "Unassigned"),
                     choice(data, "status", ("backlog", "in-progress", "done"), "backlog"),
                     choice(data, "priority", ("high", "medium", "low"), "medium"), stamp, stamp))
                message = f"Task #{cursor.lastrowid} created: {title}"
            elif resource == "incidents":
                cursor = db.execute(
                    "INSERT INTO incidents(title,service,severity,status,created_at) VALUES(?,?,?,?,?)",
                    (title, text(data, "service", 60, "ReleaseOps"),
                     choice(data, "severity", ("SEV1", "SEV2", "SEV3"), "SEV3"), "open", stamp))
                message = f"Incident #{cursor.lastrowid} opened: {title}"
            elif resource == "releases":
                supplied_environment = text(data, "environment", 30, environment)
                if supplied_environment != environment:
                    raise InvalidInput("Release environment must match the running application")
                version = text(data, "version", 100)
                action = choice(data, "action", ("deploy", "rollback", "local-rehearsal"), "deploy")
                cursor = db.execute(
                    "INSERT INTO releases(version,image,environment,action,created_at) VALUES(?,?,?,?,?)",
                    (version, text(data, "image", 300), environment, action, stamp))
                message = f"{action.capitalize()} recorded: {version} in {environment}"
            else:
                raise NotFound("Unknown resource")
            self.event(db, resource, message)
            return dict(db.execute(f"SELECT * FROM {resource} WHERE id=?", (cursor.lastrowid,)).fetchone())

    def update(self, resource, identifier, data):
        if resource not in ("tasks", "incidents"):
            raise NotFound("Resource cannot be updated")
        with self.connect() as db:
            row = db.execute(f"SELECT * FROM {resource} WHERE id=?", (identifier,)).fetchone()
            if not row:
                raise NotFound("Item was not found")
            fields = {}
            if resource == "tasks":
                for key, maximum in (("title", 160), ("owner", 60)):
                    if key in data:
                        fields[key] = text(data, key, maximum)
                if "status" in data:
                    fields["status"] = choice(data, "status", ("backlog", "in-progress", "done"))
                if "priority" in data:
                    fields["priority"] = choice(data, "priority", ("high", "medium", "low"))
                if not fields:
                    raise InvalidInput("Provide a task field to update")
                fields["updated_at"] = now()
            else:
                fields["status"] = choice(data, "status", ("open", "investigating", "resolved"))
                # A resolved incident is immutable: open a new incident for recurrence.
                if row["status"] == "resolved" and fields["status"] != "resolved":
                    raise InvalidInput("Resolved incidents cannot be reopened")
                fields["resolved_at"] = row["resolved_at"] or (now() if fields["status"] == "resolved" else None)
            assignments = ",".join(f"{key}=?" for key in fields)
            db.execute(f"UPDATE {resource} SET {assignments} WHERE id=?", (*fields.values(), identifier))
            self.event(db, resource, f"{resource.capitalize()} #{identifier} updated")
            return dict(db.execute(f"SELECT * FROM {resource} WHERE id=?", (identifier,)).fetchone())

    def probes(self, data):
        items = data.get("observations")
        if not isinstance(items, list) or not 1 <= len(items) <= 200:
            raise InvalidInput("observations must contain 1–200 health checks")
        values = []
        current = datetime.now(timezone.utc)
        for item in items:
            if not isinstance(item, dict):
                raise InvalidInput("Each observation must be an object")
            try:
                observed = datetime.fromisoformat(text(item, "observed_at", 50))
            except ValueError as exc:
                raise InvalidInput("observed_at must be an ISO 8601 timestamp") from exc
            if observed.tzinfo is None or not current - timedelta(days=2) <= observed <= current + timedelta(minutes=1):
                raise InvalidInput("observed_at must be timezone-aware and within the last 48 hours")
            latency = item.get("latency_ms")
            if isinstance(latency, bool) or not isinstance(latency, (int, float)) or not math.isfinite(latency) or not 0 <= latency <= 600000:
                raise InvalidInput("latency_ms must be a finite non-negative number")
            if type(item.get("ok")) is not bool:
                raise InvalidInput("ok must be a boolean")
            error = item.get("error", "")
            if not isinstance(error, str) or len(error) > 200:
                raise InvalidInput("error must be at most 200 characters")
            values.append((text(item, "id", 80), observed.astimezone(timezone.utc).isoformat(timespec="seconds"),
                           int(item["ok"]), latency, error))
        with self.connect() as db:
            db.executemany("INSERT OR IGNORE INTO probes VALUES(?,?,?,?,?)", values)
            cutoff = (current - timedelta(days=2)).isoformat(timespec="seconds")
            db.execute("DELETE FROM probes WHERE observed_at < ?", (cutoff,))
        return {"accepted": len(values)}

    def state(self):
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
        with self.connect() as db:
            result = {table: [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT 100")]
                      for table in ("tasks", "incidents", "releases", "events")}
            result["probes"] = [dict(row) for row in db.execute(
                "SELECT * FROM probes WHERE observed_at >= ? ORDER BY observed_at DESC LIMIT 120", (cutoff,))][::-1]
            aggregate = db.execute("SELECT COUNT(*) count,SUM(ok) passed,AVG(CASE WHEN ok=1 THEN latency_ms END) latency FROM probes WHERE observed_at >= ?", (cutoff,)).fetchone()
            count = aggregate["count"]
            result["observation"] = {
                "count": count, "passed": aggregate["passed"] or 0,
                "success_percent": round(100 * aggregate["passed"] / count, 3) if count else None,
                "latency_ms": round(aggregate["latency"], 1) if aggregate["latency"] is not None else None,
                "target_percent": 99.9, "window": "24 hours",
                "interpretation": "Sampled readiness success; not a contractual uptime measurement"}
            result["counts"] = {
                "open_incidents": db.execute("SELECT COUNT(*) FROM incidents WHERE status!='resolved'").fetchone()[0],
                "pending_tasks": db.execute("SELECT COUNT(*) FROM tasks WHERE status!='done'").fetchone()[0],
                "releases": db.execute("SELECT COUNT(*) FROM releases").fetchone()[0]}
            result["demo"] = any(item["demo"] for table in ("tasks", "incidents") for item in result[table])
            return result

    def seed_demo(self):
        with self.connect() as db:
            if db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]:
                return
            stamp = now()
            db.executemany("INSERT INTO tasks(title,owner,status,priority,created_at,updated_at,demo) VALUES(?,?,?,?,?,?,1)", [
                ("Document production rollback procedure", "Platform team", "backlog", "high", stamp, stamp),
                ("Add integration checks to the release pipeline", "Application team", "in-progress", "high", stamp, stamp),
                ("Review staging configuration", "Support team", "in-progress", "medium", stamp, stamp),
                ("Write a service readiness endpoint", "Application team", "done", "medium", stamp, stamp)])
            db.execute("INSERT INTO incidents(title,service,severity,status,created_at,demo) VALUES(?,?,?,?,?,1)",
                       ("Example: investigate a failed staging build", "CI pipeline", "SEV3", "investigating", stamp))

# API reference

All timestamps use timezone-aware UTC ISO 8601. JSON writes require `Content-Type: application/json`, one `Content-Length`, and `Authorization: Bearer <operator-token>`. Bodies are limited to 128 KiB. Reads are available inside the private lab without a token except `/api/access`.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/healthz` | Liveness: the process can answer requests |
| GET | `/readyz` | Readiness: database responds and lab failure marker is absent; 503 otherwise |
| GET | `/api/access` | Check the supplied operator token; 200 or 401 |
| GET | `/api/state` | Environment/version, tasks, incidents, releases, events, observations, aggregate counts |
| POST | `/api/tasks` | Create a task |
| PATCH | `/api/tasks/{id}` | Update title, owner, priority, or status |
| POST | `/api/incidents` | Open an incident |
| PATCH | `/api/incidents/{id}` | Change status to open, investigating, or resolved |
| POST | `/api/releases` | Record a deployment, rollback, or explicitly labeled local rehearsal |
| POST | `/api/probes` | Ingest 1–200 deduplicated readiness observations |
| GET | `/metrics` | Prometheus text metrics |

## Payload examples

Task: `{"title":"Document the deployment","owner":"Platform team","priority":"high","status":"backlog"}`. Priority: `high`, `medium`, `low`. Status: `backlog`, `in-progress`, `done`. Title limit: 160 characters; owner limit: 60.

Incident: `{"title":"Staging readiness failed","service":"ReleaseOps","severity":"SEV2"}`. Severity: `SEV1`, `SEV2`, `SEV3`. The initial status is `open`. Resolution sets `resolved_at`; resolved incidents cannot be reopened. The API permits resolving directly from open when appropriate.

Release: `{"version":"COMMIT_SHA","image":"ghcr.io/owner/repo@sha256:DIGEST","environment":"staging","action":"deploy"}`. Actions: `deploy`, `rollback`, `local-rehearsal`. The supplied environment must match the running app. An operator can record a release via the API, so the ledger is not an independently verified deployment attestation. The supplied scripts verify readiness and version before recording.

Probe: `{"observations":[{"id":"unique-observer-uuid","observed_at":"2026-10-04T00:00:00+00:00","ok":true,"latency_ms":12.5,"error":""}]}`. Replace the example timestamp with the current UTC time; the API accepts the past 48 hours and at most one minute of clock skew. Duplicate IDs are ignored. `ok` must be a boolean. Latency must be finite and between 0 and 600,000 milliseconds.

Responses: 201 for a create/ingestion, 200 for an update/read, 400 for invalid data, 401 for invalid authorization, 403 for a cross-origin write, 404 for unknown routes/items, and 503 for database/readiness failures. Errors include a request ID where relevant. Unknown static paths, database paths, and token files are never served.

Metrics include HTTP counts by bounded route/method/status, request duration sum/count, open incident count, observation count, build information, and the sampled success ratio when observations exist. In-memory HTTP counters reset when the process restarts; probe history persists in SQLite. No alert delivery system is included.

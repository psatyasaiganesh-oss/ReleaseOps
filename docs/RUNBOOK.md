# Service operations runbook

## Daily checks

1. Check `/readyz`, the dashboard’s environment/version, and recorded observer coverage.
2. Review unresolved incidents and work-board owners.
3. Inspect request error counts and JSON logs. A request ID connects a response to its log entry.
4. Before releasing, confirm pipeline results, image digest, previous image, and a recent usable backup.

Local smoke check: `python3 scripts/smoke.py`. Container staging smoke check: `python3 scripts/smoke.py --url http://127.0.0.1:18081`.

Start a staging observer:

```bash
python3 scripts/monitor.py --url http://127.0.0.1:18081 \
  --token-file .deploy/staging/api-token --spool .local/staging-monitor.json
```

For CI-host deployments, substitute `/opt/releaseops/state/staging/api-token`. Monitor spools must have a unique path per environment and one writer; do not run two observers against one spool. If a token changes, restart the observer. A failed upload retains observations; a successful upload deduplicates replayed IDs.

## Failed release

The deploy script returns nonzero and prints recent container logs. If a previous image exists, it attempts to restore it. Confirm the restored version and run a smoke check. An initial failed release has no previous image and is stopped.

Investigate in this order: image pull/authentication, runtime configuration, readiness response, database permissions/locking, and application logs. If automatic rollback fails, stop changing images, preserve logs and backups, and escalate to the platform owner with environment, failed image, previous image, timestamps, and request IDs.

Manual rollback:

```bash
bash scripts/rollback.sh staging
```

Use `PULL_IMAGE=0` for locally built images. Rollback retains the current database. Do not roll old code back across an incompatible schema migration without a tested migration recovery plan.

## Local failure drill

With the development server and observer running, create `.local/unhealthy`. Readiness returns 503 while liveness stays 200; the observer records failures. Remove the marker to recover.

```bash
touch .local/unhealthy
# Wait for at least one observer cycle; inspect /readyz and the dashboard.
rm .local/unhealthy
```

For a deterministic automated drill, run `python3 scripts/rehearse.py`. It operates an isolated temporary database and does not modify the running development workspace.

## Backups

Local consistent online backup:

```bash
python3 scripts/backup.py .local/releaseops.db .local/backups/releaseops-001.db
```

Choose a new destination for every backup. The helper uses SQLite’s online backup API and checks integrity; copying only the live `.db` file can miss committed WAL data. Store an exported copy outside the host before replacing/destroying it.

Container backup (requires the environment variables below for Compose interpolation):

```bash
export APP_ENV=staging APP_HOST_PORT=18081 IMAGE_REF=releaseops:1.0.0
export API_TOKEN="$(cat .deploy/staging/api-token)"
docker compose -p releaseops-staging exec -T app \
  python /app/scripts/backup.py /data/releaseops.db /data/backups/releaseops-001.db
```

For a CI deployment, read the token from `/opt/releaseops/state/staging/api-token`. The image value must be syntactically valid for Compose; `exec` targets the already-running project container. Export the resulting backup through `docker cp` using that container’s ID. Treat copied databases as private operational data.

## Local restore

1. Stop the application and observer. Confirm no process is writing to the database.
2. Verify the selected backup with SQLite `PRAGMA integrity_check`.
3. Preserve the current `.db`, `.db-wal`, and `.db-shm` together in a separate recovery folder.
4. Replace `.local/releaseops.db` with the backup, mode 600. Remove stale WAL/SHM sidecars from the database’s active path only after preserving them and stopping all writers.
5. Restart, smoke-test, inspect tasks/incidents, then restart the observer.

Container restoration requires stopping that environment’s container and restoring into its named volume with UID/GID 10001. Use an approved offline maintenance container and preserve the existing database/sidecars first. Never delete the environment volume to perform a code rollback.

## Incident handoff

Record impact, severity, environment, first observed time, failed release/version, checks performed, mitigation, current owner, and next update. Resolve only after readiness and an application smoke check succeed. Open a new incident if a resolved issue recurs. No paging, email, or external messaging is automatically sent by this project.

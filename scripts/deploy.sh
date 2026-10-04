#!/usr/bin/env bash
# Single-host release with readiness gating, serialized changes and rollback.
set -Eeuo pipefail
umask 077
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ENV="${1:-}"
IMAGE_REF="${2:-}"
if [[ "$APP_ENV" != staging && "$APP_ENV" != production ]]; then
  echo 'Usage: scripts/deploy.sh staging|production IMAGE_REFERENCE' >&2
  exit 2
fi
if [[ ! "$IMAGE_REF" =~ ^[a-zA-Z0-9][a-zA-Z0-9./:@_-]{0,299}$ ]]; then
  echo 'Provide a valid image reference without whitespace.' >&2
  exit 2
fi
for executable in docker python3 flock; do command -v "$executable" >/dev/null || { echo "Missing $executable" >&2; exit 2; }; done
docker compose version >/dev/null
STATE_ROOT="${STATE_DIR:-$ROOT_DIR/.deploy}"
DEPLOY_DIR="$STATE_ROOT/$APP_ENV"
mkdir -p -- "$DEPLOY_DIR"
exec 9>"$DEPLOY_DIR/deploy.lock"
flock -n 9 || { echo "A deployment to $APP_ENV is already running." >&2; exit 2; }
TOKEN_FILE="$DEPLOY_DIR/api-token"
if [[ ! -s "$TOKEN_FILE" ]]; then python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > "$TOKEN_FILE"; fi
chmod 600 "$TOKEN_FILE"
API_TOKEN="$(<"$TOKEN_FILE")"
DEPLOY_NAMESPACE="${DEPLOY_NAMESPACE:-releaseops}"
if [[ ! "$DEPLOY_NAMESPACE" =~ ^[a-z][a-z0-9-]{0,40}$ ]]; then echo 'Invalid deployment namespace.' >&2; exit 2; fi
APP_HOST_PORT="${PORT_OVERRIDE:-18081}"
if [[ "$APP_ENV" == production && -z "${PORT_OVERRIDE:-}" ]]; then APP_HOST_PORT=18080; fi
if [[ ! "$APP_HOST_PORT" =~ ^[0-9]{1,5}$ ]] || (( APP_HOST_PORT < 1024 || APP_HOST_PORT > 65535 )); then echo 'Invalid host port.' >&2; exit 2; fi
export DEPLOY_NAMESPACE
export APP_ENV IMAGE_REF API_TOKEN APP_HOST_PORT
BASE_URL="http://127.0.0.1:$APP_HOST_PORT"
PREVIOUS_IMAGE=""
if [[ -f "$DEPLOY_DIR/current-image" ]]; then PREVIOUS_IMAGE="$(<"$DEPLOY_DIR/current-image")"; fi
compose() { docker compose -p "$DEPLOY_NAMESPACE-$APP_ENV" -f "$ROOT_DIR/compose.yaml" "$@"; }
record_release() {
  RELEASE_IMAGE_REF="$IMAGE_REF" RELEASE_ACTION="$1" python3 "$ROOT_DIR/scripts/record_release.py" "$BASE_URL"
}
rollback_on_failure() {
  echo "Release failed readiness or recording checks in $APP_ENV." >&2
  compose logs --tail 30 app >&2 || true
  if [[ -n "$PREVIOUS_IMAGE" ]]; then
    IMAGE_REF="$PREVIOUS_IMAGE"; export IMAGE_REF
    if compose up -d --wait --wait-timeout "${WAIT_SECONDS:-90}" app; then
      EXPECTED_VERSION="" record_release rollback || true
      echo 'Previous image restored; database volume preserved.' >&2
    else
      echo 'Automatic rollback failed. Follow docs/RUNBOOK.md and escalate.' >&2
    fi
  else
    compose stop app || true
    echo 'Initial deployment failed; no previous image exists.' >&2
  fi
  exit 1
}
# Local images can be deployed with PULL_IMAGE=0. CI always uses a registry digest.
if [[ "${PULL_IMAGE:-1}" == 1 ]]; then compose pull app; fi
if ! compose up -d --wait --wait-timeout "${WAIT_SECONDS:-90}" app; then rollback_on_failure; fi
if ! record_release "${DEPLOY_ACTION:-deploy}"; then rollback_on_failure; fi
if [[ -n "$PREVIOUS_IMAGE" && "$PREVIOUS_IMAGE" != "$IMAGE_REF" ]]; then
  printf '%s\n' "$PREVIOUS_IMAGE" > "$DEPLOY_DIR/previous-image.tmp"
  mv -- "$DEPLOY_DIR/previous-image.tmp" "$DEPLOY_DIR/previous-image"
fi
printf '%s\n' "$IMAGE_REF" > "$DEPLOY_DIR/current-image.tmp"
mv -- "$DEPLOY_DIR/current-image.tmp" "$DEPLOY_DIR/current-image"
printf 'Release complete: %s at %s\nOperator token file: %s\n' "$APP_ENV" "$BASE_URL" "$TOKEN_FILE"

#!/usr/bin/env bash
# Run on a Docker-enabled host or GitHub-hosted CI runner.
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export STATE_DIR="$(mktemp -d)" DEPLOY_NAMESPACE="releaseops-test-$$" PULL_IMAGE=0 WAIT_SECONDS=25
export PORT_OVERRIDE="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
export APP_ENV=staging APP_HOST_PORT="$PORT_OVERRIDE" IMAGE_REF=releaseops:integration-v1
export API_TOKEN=ci-cleanup-only-placeholder-token
cleanup() {
  docker compose -p "$DEPLOY_NAMESPACE-staging" -f compose.yaml down -v >/dev/null 2>&1 || true
  rm -rf -- "$STATE_DIR"
}
trap cleanup EXIT
docker build --build-arg VERSION=integration-v1 -t releaseops:integration-v1 .
docker build --build-arg VERSION=integration-v2 -t releaseops:integration-v2 .
docker build -f tests/Dockerfile.unhealthy -t releaseops:integration-broken .
bash scripts/deploy.sh staging releaseops:integration-v1
API_TOKEN="$(<"$STATE_DIR/staging/api-token")"; export API_TOKEN
BASE_URL="http://127.0.0.1:$PORT_OVERRIDE"
TEST_URL="$BASE_URL" python3 - <<'PY'
import json, os, urllib.request
req=urllib.request.Request(os.environ['TEST_URL']+'/api/tasks', data=json.dumps({'title':'Preserve across Docker releases'}).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ['API_TOKEN']})
with urllib.request.urlopen(req) as response: assert response.status==201
PY
bash scripts/deploy.sh staging releaseops:integration-v2
if bash scripts/deploy.sh staging releaseops:integration-broken; then echo 'Unhealthy image unexpectedly passed' >&2; exit 1; fi
EXPECTED_VERSION=integration-v2 python3 scripts/smoke.py --url "$BASE_URL"
TEST_URL="$BASE_URL" python3 - <<'PY'
import json, os, urllib.request
with urllib.request.urlopen(os.environ['TEST_URL']+'/api/state') as response: state=json.load(response)
assert state['tasks'][0]['title']=='Preserve across Docker releases'
assert state['releases'][0]['action']=='rollback'
PY
[[ "$(<"$STATE_DIR/staging/current-image")" == releaseops:integration-v2 ]]
bash scripts/rollback.sh staging
EXPECTED_VERSION=integration-v1 python3 scripts/smoke.py --url "$BASE_URL"
echo 'PASS: container deployment, failed-image rollback, manual rollback, and persistent data.'

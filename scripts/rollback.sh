#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_ENV="${1:-}"
if [[ "$TARGET_ENV" != staging && "$TARGET_ENV" != production ]]; then echo 'Usage: scripts/rollback.sh staging|production' >&2; exit 2; fi
PREVIOUS_FILE="${STATE_DIR:-$ROOT_DIR/.deploy}/$TARGET_ENV/previous-image"
if [[ ! -s "$PREVIOUS_FILE" ]]; then echo 'No previous successful image is recorded.' >&2; exit 1; fi
DEPLOY_ACTION=rollback EXPECTED_VERSION="" bash "$ROOT_DIR/scripts/deploy.sh" "$TARGET_ENV" "$(<"$PREVIOUS_FILE")"

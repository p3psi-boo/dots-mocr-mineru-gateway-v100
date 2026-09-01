#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${DOTOCRM_ENV_FILE:-$ROOT/.env.docker}"

export DOTOCRM_ENV_FILE="$ENV_FILE"
docker compose \
  --project-directory "$ROOT" \
  --env-file "$ENV_FILE" \
  -f "$ROOT/compose.yaml" \
  down

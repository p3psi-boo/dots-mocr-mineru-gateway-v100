#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${DOTOCRM_ENV_FILE:-$ROOT/.env.docker}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing Docker environment file: $ENV_FILE" >&2
  echo "Copy .env.docker.example to .env.docker and set both API keys." >&2
  exit 1
fi

export DOTOCRM_ENV_FILE="$ENV_FILE"
docker compose \
  --project-directory "$ROOT" \
  --env-file "$ENV_FILE" \
  -f "$ROOT/compose.yaml" \
  up --detach --build

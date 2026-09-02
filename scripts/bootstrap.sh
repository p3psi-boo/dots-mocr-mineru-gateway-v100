#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_VERSION="${DOTOCRM_PYTHON_VERSION:-3.12}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

if [[ "${1:-}" == "--with-vllm" ]]; then
  uv sync --project "$ROOT" --python "$PYTHON_VERSION" --locked --no-dev --extra vllm
else
  uv sync --project "$ROOT" --python "$PYTHON_VERSION" --locked --no-dev
fi

if [[ ! -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  chmod 600 "$ROOT/.env"
fi

printf 'Environment ready at %s/.venv\n' "$ROOT"

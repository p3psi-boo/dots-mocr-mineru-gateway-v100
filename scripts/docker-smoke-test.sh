#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${DOTOCRM_BASE_URL:-http://127.0.0.1:8000}"

curl --fail --silent --show-error "$BASE_URL/healthz"
printf '\n'
curl --fail --silent --show-error "$BASE_URL/health"
printf '\n'

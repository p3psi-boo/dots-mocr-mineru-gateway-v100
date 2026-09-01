#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${DOTOCRM_BASE_URL:-http://[::1]:8000}"
curl -g --noproxy '*' --fail --silent --show-error "$BASE_URL/healthz"
printf '\n'
curl -g --noproxy '*' --fail --silent --show-error "$BASE_URL/health"
printf '\n'

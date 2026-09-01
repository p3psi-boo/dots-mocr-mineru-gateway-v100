#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBLIC_PORT="${DOTOCRM_PUBLIC_PORT:-8000}"
API_PORT="${DOTOCRM_API_PORT:-8010}"

sed \
  -e "s|@PUBLIC_PORT@|$PUBLIC_PORT|g" \
  -e "s|@API_PORT@|$API_PORT|g" \
  "$ROOT/deploy/nginx/dotocrm.conf.in" | \
  sudo tee /etc/nginx/sites-available/dotocrm >/dev/null
sudo ln -sfn /etc/nginx/sites-available/dotocrm /etc/nginx/sites-enabled/dotocrm
sudo nginx -t
sudo systemctl reload nginx

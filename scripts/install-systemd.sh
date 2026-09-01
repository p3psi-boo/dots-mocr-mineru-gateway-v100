#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="${DOTOCRM_USER:-${SUDO_USER:-$USER}}"

for name in dotocrm-vllm dotocrm-api; do
  sed \
    -e "s|@ROOT@|$ROOT|g" \
    -e "s|@USER@|$SERVICE_USER|g" \
    "$ROOT/deploy/systemd/$name.service.in" | \
    sudo tee "/etc/systemd/system/$name.service" >/dev/null
done

sudo systemctl daemon-reload
sudo systemctl enable dotocrm-vllm dotocrm-api
printf 'Installed systemd units for user %s at %s\n' "$SERVICE_USER" "$ROOT"

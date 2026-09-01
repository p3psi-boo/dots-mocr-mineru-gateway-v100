#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_ID="${MODELSCOPE_MODEL_ID:-dots-studio/dots.mocr}"
MODEL_DIR="${DOTOCRM_MODEL_PATH:-$ROOT/models/dots.mocr}"

mkdir -p "$(dirname "$MODEL_DIR")"
"$ROOT/.venv/bin/python" - "$MODEL_ID" "$MODEL_DIR" <<'PY'
import sys
from modelscope import snapshot_download

model_id, model_dir = sys.argv[1:]
snapshot_download(model_id, local_dir=model_dir)
print(model_dir)
PY

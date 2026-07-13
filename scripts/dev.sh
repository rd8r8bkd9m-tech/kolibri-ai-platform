#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
./scripts/doctor.sh
if [[ ! -d .venv ]]; then python3 -m venv .venv; fi
. .venv/bin/activate
python -m pip install --disable-pip-version-check -r services/api-gateway/requirements.txt
if [[ ! -d apps/shell/node_modules ]]; then (cd apps/shell && npm ci --no-audit --no-fund); fi
export PYTHONPATH="$ROOT/services/api-gateway"
export KOLIBRI_DATA_DIR="${KOLIBRI_DATA_DIR:-$ROOT/data}"
export KOLIBRI_NODE_JOIN_TOKEN="${KOLIBRI_NODE_JOIN_TOKEN:-canary-secret}"
python -m uvicorn main:app --app-dir services/api-gateway --host 127.0.0.1 --port 8191 >"$ROOT/data/api.log" 2>&1 &
API_PID=$!
cleanup(){ kill "$API_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
for _ in {1..60}; do curl -fsS http://127.0.0.1:8191/ready >/dev/null && break; sleep .25; done
(cd apps/shell && npm run dev)

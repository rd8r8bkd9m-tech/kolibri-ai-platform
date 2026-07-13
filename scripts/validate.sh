#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
./scripts/doctor.sh
if [[ ! -d .venv ]]; then python3 -m venv .venv; fi
. .venv/bin/activate
python -m pip install --disable-pip-version-check -r services/api-gateway/requirements-dev.txt
if [[ ! -d apps/shell/node_modules ]]; then (cd apps/shell && npm ci --no-audit --no-fund); fi
export PYTHONPATH="$ROOT/services/api-gateway"
export KOLIBRI_DATA_DIR="${KOLIBRI_DATA_DIR:-$ROOT/data/test}"
export KOLIBRI_NODE_JOIN_TOKEN="${KOLIBRI_NODE_JOIN_TOKEN:-node-secret}"
rm -rf "$KOLIBRI_DATA_DIR"
python -m compileall -q services/api-gateway services/node-runtime tools
python tools/validate_architecture.py
python tools/generate_openapi.py
python -m pytest -q services/api-gateway/tests
(cd apps/shell && npm test && npm run build)
if command -v cargo >/dev/null 2>&1; then cargo test --workspace; else echo "note: cargo not installed; Rust checks delegated to CI"; fi
echo "ok: Kolibri AI OS V2.1 validation passed"

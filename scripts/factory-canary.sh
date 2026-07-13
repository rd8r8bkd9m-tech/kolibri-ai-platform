#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/services/api-gateway"
python tools/run_factory_canary.py --control-url "${1:-http://127.0.0.1:8191}" --token "${KOLIBRI_NODE_JOIN_TOKEN:-canary-secret}" --owner-token "${KOLIBRI_OWNER_ACCESS_TOKEN:-canary-owner-secret}"

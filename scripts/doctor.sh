#!/usr/bin/env bash
set -euo pipefail
need(){ command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 1; }; }
need python3
need node
need npm
need curl
python3 - <<'PY'
import sys
assert sys.version_info >= (3, 12), f"Python 3.12+ required, got {sys.version}"
PY
node -e 'const [maj]=process.versions.node.split(".").map(Number); if(maj<22) process.exit(1)'
echo "ok: doctor passed"

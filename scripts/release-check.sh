#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
rm -rf var/release-check release-evidence
mkdir -p var/release-check release-evidence
./scripts/validate.sh
. .venv/bin/activate
python tools/security_scan.py
python tools/generate_sbom.py
python tools/run_browser_e2e.py
PYTHONPATH="$ROOT/services/api-gateway:$ROOT/tools" python tools/run_factory_release_check.py
python tools/build_release_summary.py
echo "ok: Kolibri AI OS V2.1 release check passed"

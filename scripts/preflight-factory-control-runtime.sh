#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$(pwd)}"
UNIT="${ROOT}/ops/systemd/kolibri-factory-control.service"

if [[ ! -f "${ROOT}/ops/factory_control.py" ]]; then
  echo "factory_control_missing:${ROOT}/ops/factory_control.py" >&2
  exit 1
fi

if [[ ! -f "${ROOT}/ops/telegram_superfactory.py" ]]; then
  echo "telegram_superfactory_missing:${ROOT}/ops/telegram_superfactory.py" >&2
  exit 1
fi

if [[ ! -f "${UNIT}" ]]; then
  echo "factory_control_unit_missing:${UNIT}" >&2
  exit 1
fi

if ! grep -qx "WorkingDirectory=/opt/kolibri-ai-platform" "${UNIT}"; then
  echo "factory_control_unit_missing_working_directory" >&2
  exit 1
fi

if ! grep -qx "ExecStart=/usr/bin/python3 /opt/kolibri-ai-platform/ops/factory_control.py" "${UNIT}"; then
  echo "factory_control_unit_uses_unsafe_launcher" >&2
  exit 1
fi

KOLIBRI_REPO_ROOT="${ROOT}" KOLIBRI_OPS_DIR="${ROOT}/ops" python3 - <<'PY'
import importlib.util
import os
import sys
from pathlib import Path

root = Path(os.environ["KOLIBRI_REPO_ROOT"])
spec = importlib.util.spec_from_file_location("factory_control_preflight", root / "ops" / "factory_control.py")
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

required_get = {
    "/v1/health",
    "/v1/fleet/nodes",
    "/v1/fleet/topology",
    "/v1/fleet/route",
    "/v1/fleet/capabilities",
    "/v1/models",
}
required_fabric = {
    "/v1/fabric/health",
    "/v1/fabric/policy",
    "/v1/fabric/routes",
}
declared_get = set(module.PROMPT3_REQUIRED_ENDPOINTS["GET"])
missing = sorted(required_get - declared_get)
if missing:
    raise SystemExit(f"factory_control_required_get_missing:{missing}")

source = (root / "ops" / "factory_control.py").read_text(encoding="utf-8")
missing_fabric = sorted(path for path in required_fabric if f'path == "{path}"' not in source)
if missing_fabric:
    raise SystemExit(f"factory_control_fabric_routes_missing:{missing_fabric}")

nodes = module.fabric_nodes([])
if {"home", "main", "uiap", "qjns", "9fts", "new"} - {node["node_id"] for node in nodes}:
    raise SystemExit("factory_control_fabric_catalog_incomplete")

print("factory_control_runtime_preflight=ok")
PY

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE="$ROOT/contracts/kolibri-os-v1/fixtures/task-lifecycle-parity.json"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/kolibri-shadow-parity.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

cargo run --quiet --manifest-path "$ROOT/Cargo.toml" -p kolibri-task-shadow -- replay \
  "$FIXTURE" --assert-expected >"$TMP_DIR/rust.json"
python3 "$ROOT/scripts/rust_shadow_python_parity.py" \
  "$FIXTURE" --assert-expected >"$TMP_DIR/python.json"

python3 - "$TMP_DIR/rust.json" "$TMP_DIR/python.json" <<'PY'
import json
import pathlib
import sys

rust = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
python = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
if rust != python:
    raise SystemExit("Rust/Python task shadow parity mismatch")
print(
    "Rust/Python task shadow parity: PASS "
    f"task={rust['task_id']} events={rust['event_count']} "
    f"trace={rust['trace_sha256']}"
)
PY

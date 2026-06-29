#!/usr/bin/env bash
set -u

CONTROL_URL="${KOLIBRI_FACTORY_CONTROL_URL:-http://10.99.0.2:9101}"
RECOVERY_ENVELOPE="${1:-ops/envelopes/KOL-SERVER-KFRM-RUNTIME-RECOVERY-20260629.json}"
PROBE_ENVELOPE="${PROBE_ENVELOPE:-ops/envelopes/KOL-SERVER-KFRM-PROBE-20260629.json}"
PROBE_TASK_ID="${PROBE_TASK_ID:-KOL-SERVER-KFRM-PROBE-20260629}"
EXPECTED_PROBE_IDEMPOTENCY="${EXPECTED_PROBE_IDEMPOTENCY:-server-kfrm:read-only-probe:2026-06-29}"

blockers=()
notes=()

add_blocker() {
  blockers+=("$1")
}

add_note() {
  notes+=("$1")
}

json_get() {
  local path="$1"
  local expr="$2"
  python3 - "$path" "$expr" <<'PY'
import json
import sys

path, expr = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    value = json.load(fh)
for part in expr.split("."):
    if not part:
        continue
    if isinstance(value, dict):
        value = value.get(part)
    else:
        value = None
        break
if isinstance(value, (dict, list)):
    print(json.dumps(value, sort_keys=True))
elif value is not None:
    print(value)
PY
}

http_get() {
  local path="$1"
  local out="$2"
  local code
  code="$(
    curl -fsS --max-time 20 \
      -w '%{http_code}' \
      -o "$out" \
      "$CONTROL_URL$path" 2>"$out.err" || true
  )"
  printf '%s' "$code"
}

json_value() {
  local path="$1"
  local expr="$2"
  python3 - "$path" "$expr" <<'PY'
import json
import sys

path, expr = sys.argv[1], sys.argv[2]
try:
    with open(path, encoding="utf-8") as fh:
        value = json.load(fh)
except Exception:
    sys.exit(1)
for part in expr.split("."):
    if not part:
        continue
    if isinstance(value, dict):
        value = value.get(part)
    else:
        value = None
        break
if isinstance(value, bool):
    print("true" if value else "false")
elif value is not None:
    print(value)
PY
}

validate_envelope() {
  local path="$1"
  local label="$2"
  if [[ ! -f "$path" ]]; then
    add_blocker "$label missing: $path"
    return
  fi
  if ! python3 -m json.tool "$path" >/dev/null; then
    add_blocker "$label is not valid JSON: $path"
    return
  fi
  add_note "$label JSON is valid: $path"
}

tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/server-kfrm-guard.XXXXXX")"
trap 'rm -rf "$tmpdir"' EXIT

validate_envelope "$RECOVERY_ENVELOPE" "recovery envelope"
validate_envelope "$PROBE_ENVELOPE" "probe envelope"

if [[ -f "$PROBE_ENVELOPE" ]]; then
  probe_id="$(json_get "$PROBE_ENVELOPE" "task_id" 2>/dev/null || true)"
  probe_key="$(json_get "$PROBE_ENVELOPE" "idempotency_key" 2>/dev/null || true)"
  probe_target="$(json_get "$PROBE_ENVELOPE" "target_node" 2>/dev/null || true)"
  probe_kind="$(json_get "$PROBE_ENVELOPE" "kind" 2>/dev/null || true)"
  if [[ "$probe_id" != "$PROBE_TASK_ID" ]]; then
    add_blocker "probe envelope task_id is '$probe_id', expected '$PROBE_TASK_ID'"
  fi
  if [[ "$probe_key" != "$EXPECTED_PROBE_IDEMPOTENCY" ]]; then
    add_blocker "probe idempotency_key is '$probe_key', expected '$EXPECTED_PROBE_IDEMPOTENCY'"
  fi
  if [[ "$probe_target" != "server-kfrm" ]]; then
    add_blocker "probe target_node is '$probe_target', expected 'server-kfrm'"
  fi
  if [[ "$probe_kind" != "read_only_probe" ]]; then
    add_blocker "probe kind is '$probe_kind', expected 'read_only_probe'"
  fi
fi

if [[ -f "$RECOVERY_ENVELOPE" ]]; then
  recovery_id="$(json_get "$RECOVERY_ENVELOPE" "task_id" 2>/dev/null || true)"
  recovery_key="$(json_get "$RECOVERY_ENVELOPE" "idempotency_key" 2>/dev/null || true)"
  recovery_goal="$(json_get "$RECOVERY_ENVELOPE" "goal" 2>/dev/null || true)"
  if [[ -z "$recovery_id" ]]; then
    add_blocker "recovery envelope has no task_id"
  fi
  if [[ -z "$recovery_key" ]]; then
    add_blocker "recovery envelope has no idempotency_key"
  fi
  if [[ "$recovery_goal" != *"Do not run FormulaLM"* ]]; then
    add_blocker "recovery envelope goal does not include the FormulaLM/LLM guardrail"
  fi
fi

health_file="$tmpdir/health.json"
health_code="$(http_get "/health" "$health_file")"
if [[ "$health_code" != "200" ]]; then
  add_blocker "Control Plane /health unavailable at $CONTROL_URL (HTTP ${health_code:-curl_failed})"
else
  health_status="$(json_value "$health_file" "status" 2>/dev/null || true)"
  if [[ "$health_status" != "ok" ]]; then
    add_blocker "Control Plane /health status is '$health_status', expected 'ok'"
  else
    add_note "Control Plane /health is ok"
  fi
fi

nodes_file="$tmpdir/nodes.json"
nodes_code="$(http_get "/v1/nodes" "$nodes_file")"
if [[ "$nodes_code" != "200" ]]; then
  add_blocker "Control Plane /v1/nodes unavailable at $CONTROL_URL (HTTP ${nodes_code:-curl_failed})"
else
  node_summary="$(
    python3 - "$nodes_file" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    payload = json.load(fh)
nodes = payload.get("nodes", payload if isinstance(payload, list) else [])
if isinstance(nodes, dict):
    nodes = list(nodes.values())
server = None
mesh = None
generic_fresh = False
for node in nodes:
    if not isinstance(node, dict):
        continue
    node_id = node.get("node_id") or node.get("id")
    capabilities = node.get("capabilities") or []
    fresh = node.get("fresh")
    if node_id == "server-kfrm":
        server = node
    if node_id == "mesh-server-kfrm":
        mesh = node
    if fresh is True and "generic_implementation" in capabilities:
        generic_fresh = True
print(json.dumps({
    "server_present": server is not None,
    "server_fresh": None if server is None else server.get("fresh"),
    "server_health": None if server is None else server.get("health"),
    "server_draining": None if server is None else server.get("draining"),
    "server_capabilities": [] if server is None else server.get("capabilities", []),
    "mesh_present": mesh is not None,
    "fresh_generic_executor_present": generic_fresh,
}, sort_keys=True))
PY
  )"
  printf '%s\n' "$node_summary" >"$tmpdir/node-summary.json"
  server_present="$(json_value "$tmpdir/node-summary.json" "server_present" 2>/dev/null || true)"
  server_fresh="$(json_value "$tmpdir/node-summary.json" "server_fresh" 2>/dev/null || true)"
  fresh_generic="$(json_value "$tmpdir/node-summary.json" "fresh_generic_executor_present" 2>/dev/null || true)"
  if [[ "$server_present" != "true" ]]; then
    add_blocker "executor node server-kfrm is not present in /v1/nodes"
  fi
  if [[ "$server_fresh" != "true" ]]; then
    add_note "server-kfrm is not fresh; recovery envelope may still be useful as SRE orchestration, not as proof of node readiness"
  fi
  if [[ "$fresh_generic" != "true" ]]; then
    add_blocker "no fresh generic_implementation executor is visible for the recovery orchestration task"
  fi
fi

probe_file="$tmpdir/probe.json"
probe_code="$(http_get "/v1/tasks/$PROBE_TASK_ID" "$probe_file")"
case "$probe_code" in
  200)
    state="$(json_value "$probe_file" "state" 2>/dev/null || true)"
    task_id="$(json_value "$probe_file" "task_id" 2>/dev/null || true)"
    live_key="$(json_value "$probe_file" "idempotency_key" 2>/dev/null || true)"
    lease_owner="$(json_value "$probe_file" "lease_owner" 2>/dev/null || true)"
    case "$state" in
      queued|leased|running|completed|failed|cancelled|dead_letter)
        add_note "probe exists as $task_id with state=$state lease_owner=${lease_owner:-none}"
        ;;
      *)
        add_blocker "probe exists but has unknown state '$state'"
        ;;
    esac
    if [[ -n "$live_key" && "$live_key" != "$EXPECTED_PROBE_IDEMPOTENCY" ]]; then
      add_blocker "live probe idempotency_key is '$live_key', expected '$EXPECTED_PROBE_IDEMPOTENCY'"
    fi
    ;;
  404)
    add_blocker "probe task $PROBE_TASK_ID is absent; submit probe only after a separate operator decision"
    ;;
  *)
    add_blocker "cannot read probe task $PROBE_TASK_ID (HTTP ${probe_code:-curl_failed})"
    ;;
esac

printf 'server-kfrm submission guard\n'
printf 'control_url=%s\n' "$CONTROL_URL"
printf 'recovery_envelope=%s\n' "$RECOVERY_ENVELOPE"
printf 'probe_envelope=%s\n' "$PROBE_ENVELOPE"

if ((${#notes[@]} > 0)); then
  printf '\nnotes:\n'
  for note in "${notes[@]}"; do
    printf -- '- %s\n' "$note"
  done
fi

if ((${#blockers[@]} > 0)); then
  printf '\nblockers:\n'
  for blocker in "${blockers[@]}"; do
    printf -- '- %s\n' "$blocker"
  done
  printf '\nsafe_to_submit=false\n'
  exit 1
fi

printf '\nsafe_to_submit=true\n'
printf 'submit_command:\n'
printf 'KOLIBRI_FACTORY_CONTROL_URL=%q ops/kolibri-dispatch --control-url %q submit --file %q\n' \
  "$CONTROL_URL" "$CONTROL_URL" "$RECOVERY_ENVELOPE"

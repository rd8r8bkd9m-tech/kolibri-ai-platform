#!/usr/bin/env bash
# One-time owner-controlled repair that converges every existing Agent Host on
# the dynamic Home Control Plane. Normal product releases remain API-only.

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MANIFEST=""
EXPECTED=21
CANARY=agent09
APPLY=false
CANARY_ONLY=false
ONLY_NODE=""
RUN_ID="home-only-$(date -u +%Y%m%dT%H%M%SZ)"

usage() {
  echo "usage: $0 --manifest FILE [--expect 21] [--canary NODE] --apply" >&2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --manifest) MANIFEST=${2:?missing manifest}; shift 2 ;;
    --expect) EXPECTED=${2:?missing count}; shift 2 ;;
    --canary) CANARY=${2:?missing node}; shift 2 ;;
    --apply) APPLY=true; shift ;;
    --canary-only) CANARY_ONLY=true; shift ;;
    --only-node) ONLY_NODE=${2:?missing node}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
done

[ -f "$MANIFEST" ] || { echo "manifest is required" >&2; exit 2; }
case "$EXPECTED" in ''|*[!0-9]*) echo "invalid expected count" >&2; exit 2 ;; esac
case "$CANARY" in ''|*[!A-Za-z0-9._-]*) echo "invalid canary" >&2; exit 2 ;; esac
case "$ONLY_NODE" in *[!A-Za-z0-9._-]*) echo "invalid only-node" >&2; exit 2 ;; esac
command -v jq >/dev/null
command -v ssh >/dev/null
command -v scp >/dev/null

RUNTIME_FILES=(
  ops/agent_host.py
  ops/control_plane_endpoint.py
  ops/runner_access.py
  ops/runner-access.default.json
  ops/release_authority.py
  ops/release_helper.py
  ops/release_installer.py
  ops/mesh_registry.py
  ops/mesh-apply-peers
  ops/systemd/kolibri-agent-host.service
  ops/systemd/kolibri-mesh-apply-peers.service
  ops/systemd/kolibri-release-helper.service
  ops/systemd/kolibri-release-helper.socket
)
for file in "${RUNTIME_FILES[@]}"; do
  [ -f "$ROOT_DIR/$file" ] || { echo "missing runtime file: $file" >&2; exit 2; }
done

jq -e --argjson expected "$EXPECTED" --arg canary "$CANARY" '
  (.peers | type == "object") and
  ([.peers[] | .node_id] | length == $expected) and
  ([.peers[] | .node_id] | unique | length == $expected) and
  ([.peers[] | .mesh_ip] | unique | length == $expected) and
  ([.peers[] | select(.node_id == "home")] | length == 1) and
  ([.peers[] | select(.node_id == $canary)] | length == 1) and
  (all(.peers[];
    ((.rollout_stage // .labels.rollout_stage // "worker") as $stage |
      ["quorum", "worker", "last"] | index($stage)) != null
  ))
' "$MANIFEST" >/dev/null || { echo "manifest/canary validation failed" >&2; exit 2; }
if [ -n "$ONLY_NODE" ]; then
  jq -e --arg node "$ONLY_NODE" 'any(.peers[]; .node_id == $node)' "$MANIFEST" >/dev/null || {
    echo "only-node is not in manifest" >&2
    exit 2
  }
fi

HOME_IP=$(jq -r '.peers[] | select(.node_id == "home") | .mesh_ip' "$MANIFEST")
NODES=$(mktemp)
trap 'rm -f "$NODES"' EXIT
jq -r '.peers[] | [.node_id,.mesh_ip,(.rollout_stage // .labels.rollout_stage // "worker")] | @tsv' "$MANIFEST" | sort >"$NODES"

echo "run_id=$RUN_ID nodes=$EXPECTED home=$HOME_IP canary=$CANARY apply=$APPLY"
while IFS=$'\t' read -r node ip rollout_stage; do
  [ -z "$ONLY_NODE" ] || [ "$node" = "$ONLY_NODE" ] || continue
  ssh -o BatchMode=yes -o ConnectTimeout=6 "root@$ip" true </dev/null
  printf 'preflight_ok\t%s\t%s\t%s\n' "$node" "$ip" "$rollout_stage"
done <"$NODES"

if [ "$APPLY" != true ]; then
  echo "dry_run_complete"
  exit 0
fi

stage_node() {
  local node=$1 ip=$2 remote=/tmp/kolibri-home-only-$RUN_ID
  ssh "root@$ip" "install -d -m700 '$remote'" </dev/null
  scp -q \
    "$ROOT_DIR/ops/agent_host.py" \
    "$ROOT_DIR/ops/control_plane_endpoint.py" \
    "$ROOT_DIR/ops/runner_access.py" \
    "$ROOT_DIR/ops/runner-access.default.json" \
    "$ROOT_DIR/ops/release_authority.py" \
    "$ROOT_DIR/ops/release_helper.py" \
    "$ROOT_DIR/ops/release_installer.py" \
    "$ROOT_DIR/ops/mesh_registry.py" \
    "$ROOT_DIR/ops/mesh-apply-peers" \
    "$ROOT_DIR/ops/systemd/kolibri-agent-host.service" \
    "$ROOT_DIR/ops/systemd/kolibri-mesh-apply-peers.service" \
    "$ROOT_DIR/ops/systemd/kolibri-release-helper.service" \
    "$ROOT_DIR/ops/systemd/kolibri-release-helper.socket" \
    "root@$ip:$remote/"
}

rollback_node() {
  local node=$1 ip=$2
  echo "rollback_start node=$node" >&2
  ssh "root@$ip" /bin/bash -s -- "$RUN_ID" <<'REMOTE'
set -euo pipefail
backup=/var/backups/kolibri/$1
[ -d "$backup" ] || { echo "rollback backup missing" >&2; exit 1; }
rm -f /etc/systemd/system/kolibri-agent-host.service.d/99-home-only.conf
for path in \
  /usr/local/bin/kolibri-agent-host \
  /usr/local/lib/kolibri/control_plane_endpoint.py \
  /usr/local/lib/kolibri/runner_access.py \
  /etc/kolibri/runner-access.json \
  /usr/local/lib/kolibri/release_authority.py \
  /usr/local/lib/kolibri/release_helper.py \
  /usr/local/lib/kolibri/release_installer.py \
  /usr/local/lib/kolibri/mesh_registry.py \
  /usr/local/sbin/kolibri-mesh-apply-peers \
  /etc/kolibri-agent-host.env \
  /etc/systemd/system/kolibri-agent-host.service \
  /etc/systemd/system/kolibri-agent-host.service.d/99-home-only.conf \
  /etc/systemd/system/kolibri-mesh-apply-peers.service \
  /etc/systemd/system/kolibri-release-helper.service \
  /etc/systemd/system/kolibri-release-helper.socket; do
  [ -e "$backup$path" ] && cp -a "$backup$path" "$path"
done
if [ ! -e "$backup/etc/systemd/system/kolibri-mesh-apply-peers.service" ]; then
  systemctl disable --now kolibri-mesh-apply-peers.service >/dev/null 2>&1 || true
  rm -f /etc/systemd/system/kolibri-mesh-apply-peers.service
fi
chmod 0755 /usr/local/lib/kolibri 2>/dev/null || true
systemctl daemon-reload
systemctl restart kolibri-agent-host.service || true
if grep -qx active "$backup/factory-control.active" 2>/dev/null; then
  systemctl start kolibri-factory-control.service || true
fi
if grep -qx enabled "$backup/factory-control.enabled" 2>/dev/null; then
  systemctl enable kolibri-factory-control.service || true
fi
printf 'rolled_back\n' >"$backup/status"
REMOTE
  echo "rollback_complete node=$node" >&2
}

apply_node() {
  local node=$1 ip=$2 rollout_stage=$3 remote=/tmp/kolibri-home-only-$RUN_ID
  [ "$node" != "$CANARY" ] || rollout_stage=canary
  stage_node "$node" "$ip"
  if ! ssh "root@$ip" /bin/bash -s -- "$RUN_ID" "$node" "$HOME_IP" "$rollout_stage" <<'REMOTE'
set -euo pipefail
run_id=$1
node_id=$2
home_ip=$3
rollout_stage=$4
stage=/tmp/kolibri-home-only-$run_id
backup=/var/backups/kolibri/$run_id
install -d -m700 "$backup"
install -d -m755 /usr/local/lib/kolibri /etc/kolibri

for path in \
  /usr/local/bin/kolibri-agent-host \
  /usr/local/lib/kolibri/control_plane_endpoint.py \
  /usr/local/lib/kolibri/runner_access.py \
  /etc/kolibri/runner-access.json \
  /usr/local/lib/kolibri/release_authority.py \
  /usr/local/lib/kolibri/release_helper.py \
  /usr/local/lib/kolibri/release_installer.py \
  /usr/local/lib/kolibri/mesh_registry.py \
  /usr/local/sbin/kolibri-mesh-apply-peers \
  /etc/kolibri-agent-host.env \
  /etc/systemd/system/kolibri-agent-host.service \
  /etc/systemd/system/kolibri-agent-host.service.d/99-home-only.conf \
  /etc/systemd/system/kolibri-mesh-apply-peers.service \
  /etc/systemd/system/kolibri-release-helper.service \
  /etc/systemd/system/kolibri-release-helper.socket; do
  if [ -e "$path" ]; then
    mkdir -p "$backup$(dirname "$path")"
    cp -a "$path" "$backup$path"
    sha256sum "$path" >>"$backup/checksums.before"
  fi
done
systemctl is-active kolibri-factory-control.service >"$backup/factory-control.active" 2>/dev/null || true
systemctl is-enabled kolibri-factory-control.service >"$backup/factory-control.enabled" 2>/dev/null || true

getent group kolibri-agent >/dev/null || groupadd --system kolibri-agent
id -u kolibri-agent >/dev/null 2>&1 || useradd --system --gid kolibri-agent --home-dir /var/lib/kolibri-agent --shell /usr/sbin/nologin kolibri-agent
install -d -m755 /usr/local/lib/kolibri /etc/systemd/system/kolibri-agent-host.service.d
install -d -m755 /opt/kolibri-ai /opt/kolibri-ai/releases /var/lib/kolibri-release
install -d -m700 /var/lib/kolibri-release/artifacts
install -d -o kolibri-agent -g kolibri-agent -m700 \
  /var/lib/kolibri-agent /var/lib/kolibri-agent/worktrees /var/lib/kolibri-agent/artifacts

install -m755 "$stage/agent_host.py" /usr/local/bin/kolibri-agent-host
install -m644 "$stage/control_plane_endpoint.py" /usr/local/lib/kolibri/control_plane_endpoint.py
install -m644 "$stage/runner_access.py" /usr/local/lib/kolibri/runner_access.py
install -m644 "$stage/runner-access.default.json" /etc/kolibri/runner-access.json
install -m644 "$stage/release_authority.py" /usr/local/lib/kolibri/release_authority.py
install -m644 "$stage/release_helper.py" /usr/local/lib/kolibri/release_helper.py
install -m644 "$stage/release_installer.py" /usr/local/lib/kolibri/release_installer.py
install -m755 "$stage/mesh_registry.py" /usr/local/lib/kolibri/mesh_registry.py
install -m755 "$stage/mesh-apply-peers" /usr/local/sbin/kolibri-mesh-apply-peers
install -m644 "$stage/kolibri-agent-host.service" /etc/systemd/system/kolibri-agent-host.service
install -m644 "$stage/kolibri-mesh-apply-peers.service" /etc/systemd/system/kolibri-mesh-apply-peers.service
install -m644 "$stage/kolibri-release-helper.service" /etc/systemd/system/kolibri-release-helper.service
install -m644 "$stage/kolibri-release-helper.socket" /etc/systemd/system/kolibri-release-helper.socket
cat >/etc/systemd/system/kolibri-agent-host.service.d/99-home-only.conf <<'EOF'
[Service]
UnsetEnvironment=KOLIBRI_FACTORY_CONTROL_URL KOLIBRI_FACTORY_CONTROL_URLS
ExecStart=
ExecStart=/usr/local/bin/kolibri-agent-host
EOF
chmod 0644 /etc/systemd/system/kolibri-agent-host.service.d/99-home-only.conf

env_tmp=$(mktemp)
if [ -f /etc/kolibri-agent-host.env ]; then
  awk '
    !/^KOLIBRI_FACTORY_CONTROL_URLS?=/ &&
    !/^KOLIBRI_NODE_ID=/ &&
    !/^KOLIBRI_NODE_LABELS_JSON=/
  ' /etc/kolibri-agent-host.env >"$env_tmp"
fi
printf 'KOLIBRI_NODE_ID=%s\n' "$node_id" >>"$env_tmp"
printf 'KOLIBRI_NODE_LABELS_JSON={"physical_node_id":"%s","rollout_stage":"%s"}\n' "$node_id" "$rollout_stage" >>"$env_tmp"
grep -q '^KOLIBRI_AGENT_CAPABILITIES=' "$env_tmp" 2>/dev/null || printf 'KOLIBRI_AGENT_CAPABILITIES=generic_implementation,read_only_probe\n' >>"$env_tmp"
grep -q '^KOLIBRI_MESH_MEMBERSHIP_MANIFEST=' "$env_tmp" 2>/dev/null || printf 'KOLIBRI_MESH_MEMBERSHIP_MANIFEST=/var/lib/kolibri-mesh/peers.json\n' >>"$env_tmp"
grep -q '^KOLIBRI_RUNNER_ACCESS_MANIFEST=' "$env_tmp" 2>/dev/null || printf 'KOLIBRI_RUNNER_ACCESS_MANIFEST=/etc/kolibri/runner-access.json\n' >>"$env_tmp"
install -m640 -o root -g kolibri-agent "$env_tmp" /etc/kolibri-agent-host.env
rm -f "$env_tmp"

PYTHONPATH=/usr/local/lib/kolibri /usr/bin/python3 /usr/local/lib/kolibri/runner_access.py --manifest /etc/kolibri/runner-access.json >/dev/null
PYTHONPATH=/usr/local/lib/kolibri /usr/bin/python3 /usr/local/lib/kolibri/control_plane_endpoint.py --print-url | grep -Fx "http://$home_ip:9101" >/dev/null
curl -fsS --max-time 5 "http://$home_ip:9101/health" >/dev/null
systemctl daemon-reload
systemctl enable --now kolibri-mesh-apply-peers.service
systemctl enable --now kolibri-release-helper.socket
systemctl enable kolibri-agent-host.service
systemctl restart kolibri-agent-host.service
for attempt in $(seq 1 20); do
  systemctl is-active --quiet kolibri-agent-host.service && break
  sleep 1
done
systemctl is-active --quiet kolibri-agent-host.service
restarts=$(systemctl show kolibri-agent-host.service -p NRestarts --value)
sleep 5
systemctl is-active --quiet kolibri-agent-host.service
[ "$(systemctl show kolibri-agent-host.service -p NRestarts --value)" = "$restarts" ]

# Only Home may remain a Control Plane. Stop legacy authorities after the new
# Agent Host has proved it can resolve and reach Home.
if [ "$node_id" != home ] && systemctl cat kolibri-factory-control.service >/dev/null 2>&1; then
  systemctl disable --now kolibri-factory-control.service || true
  systemctl is-active --quiet kolibri-factory-control.service && exit 41 || true
  systemctl is-enabled --quiet kolibri-factory-control.service && exit 42 || true
fi

rm -rf "$stage"
printf 'applied\n' >"$backup/status"
REMOTE
  then
    rollback_node "$node" "$ip"
    return 1
  fi
  printf 'applied_ok\t%s\t%s\n' "$node" "$ip"
}

verify_node_execution() {
  local node=$1
  local control="http://$HOME_IP:9101"
  local deadline=$((SECONDS + 90))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if curl -fsS --max-time 5 "$control/v1/nodes/$node" | jq -e --arg node "$node" '
      .node_id == $node and
      .freshness == "fresh" and
      .health == "online" and
      (.capabilities | index("read_only_probe")) != null
    ' >/dev/null; then
      break
    fi
    sleep 2
  done
  [ "$SECONDS" -lt "$deadline" ] || { echo "registration gate failed: $node" >&2; return 1; }

  local idem="$RUN_ID-$node-probe"
  local task_id
  task_id=$(jq -nc --arg node "$node" --arg idem "$idem" '{
    kind:"read_only_probe",
    idempotency_key:$idem,
    target_node:$node,
    required_capability:"read_only_probe",
    constraints:{read_only:true},
    write_scope:[],
    max_retries:0
  }' | curl -fsS --max-time 10 -H 'Content-Type: application/json' -X POST "$control/v1/tasks" --data-binary @- | jq -r '.task_id // empty')
  [ -n "$task_id" ] || { echo "probe submission failed: $node" >&2; return 1; }

  deadline=$((SECONDS + 90))
  while [ "$SECONDS" -lt "$deadline" ]; do
    local task state
    task=$(curl -fsS --max-time 5 "$control/v1/tasks/$task_id")
    state=$(jq -r '.state // empty' <<<"$task")
    if [ "$state" = completed ]; then
      jq -e --arg node "$node" '
        (.attempt_id | type == "string" and length > 0) and
        (.lease_owner | startswith($node + ":")) and
        (.result.status == "completed") and
        (.result.node_id == $node) and
        (.result.attempt_id == .attempt_id) and
        (.result.result_path | type == "string" and length > 0) and
        (.error_type == null)
      ' <<<"$task" >/dev/null || { echo "probe evidence invalid: $node" >&2; return 1; }
      printf 'execution_gate_ok\t%s\t%s\n' "$node" "$task_id"
      return 0
    fi
    case "$state" in failed|dead_letter|cancelled) echo "probe terminal failure: $node $state" >&2; return 1 ;; esac
    sleep 2
  done
  echo "probe timed out: $node" >&2
  return 1
}

lookup_ip() { awk -F '\t' -v node="$1" '$1==node {print $2}' "$NODES"; }
lookup_stage() { awk -F '\t' -v node="$1" '$1==node {print $3}' "$NODES"; }

# Canary first, Home second, then manifest-declared stages. New members default
# to the worker stage; no physical worker names are embedded in the rollout.
if [ -n "$ONLY_NODE" ]; then
  apply_node "$ONLY_NODE" "$(lookup_ip "$ONLY_NODE")" "$(lookup_stage "$ONLY_NODE")"
  verify_node_execution "$ONLY_NODE" || {
    rollback_node "$ONLY_NODE" "$(lookup_ip "$ONLY_NODE")"
    exit 1
  }
  echo "single_node_complete run_id=$RUN_ID node=$ONLY_NODE"
  exit 0
fi
apply_node "$CANARY" "$(lookup_ip "$CANARY")" "$(lookup_stage "$CANARY")"
verify_node_execution "$CANARY" || {
  rollback_node "$CANARY" "$(lookup_ip "$CANARY")"
  exit 1
}
if [ "$CANARY_ONLY" = true ]; then
  echo "canary_complete run_id=$RUN_ID"
  exit 0
fi
apply_node home "$(lookup_ip home)" quorum
for desired_stage in quorum worker last; do
  while IFS=$'\t' read -r node ip rollout_stage; do
    case "$node" in "$CANARY"|home) continue ;; esac
    [ "$rollout_stage" = "$desired_stage" ] || continue
    apply_node "$node" "$ip" "$rollout_stage"
  done <"$NODES"
done

echo "rollout_complete run_id=$RUN_ID"

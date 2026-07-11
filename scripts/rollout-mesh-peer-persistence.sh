#!/usr/bin/env bash
# Persist the replicated WireGuard peer set on every manifest member.
#
# Default mode is a read-only plan.  --apply is the only mutation gate.  The
# apply path installs the checksum-bound helper/runtime/unit, starts only the
# peer apply oneshot, and proves that wg-quick itself was not restarted.

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MANIFEST="${KOLIBRI_MESH_MEMBERSHIP_MANIFEST:-}"
HOME_TARGET="${KOLIBRI_HOME_SSH_TARGET:-home}"
SSH_USER="${KOLIBRI_FLEET_SSH_USER:-root}"
EXPECTED="${KOLIBRI_EXPECTED_SERVERS:-21}"
TIMEOUT="${KOLIBRI_FLEET_PROBE_TIMEOUT:-6}"
HANDSHAKE_STALE="${KOLIBRI_MESH_HANDSHAKE_STALE_SECONDS:-180}"
HANDSHAKE_WAIT="${KOLIBRI_MESH_HANDSHAKE_WAIT_SECONDS:-45}"
ONLY_NODE=""
CANARY=""
APPLY=false
RUN_ID="mesh-peer-persistence-$(date -u +%Y%m%dT%H%M%SZ)"

usage() {
  cat >&2 <<'EOF'
usage: rollout-mesh-peer-persistence.sh --manifest FILE
       [--expect 21] [--home SSH_TARGET] [--ssh-user USER]
       [--only-node NODE | --canary NODE] [--apply]

Without --apply this command performs read-only manifest, transport, fragment,
unit, runtime-peer and handshake discovery.  --canary selects exactly one
manifest member and is the recommended first mutation wave.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --manifest) MANIFEST=${2:?missing manifest}; shift 2 ;;
    --expect) EXPECTED=${2:?missing expected count}; shift 2 ;;
    --home) HOME_TARGET=${2:?missing Home target}; shift 2 ;;
    --ssh-user) SSH_USER=${2:?missing SSH user}; shift 2 ;;
    --only-node) ONLY_NODE=${2:?missing node}; shift 2 ;;
    --canary) CANARY=${2:?missing canary node}; shift 2 ;;
    --apply) APPLY=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
done

[ -f "$MANIFEST" ] || { echo "manifest is required" >&2; exit 2; }
[ -z "$ONLY_NODE" ] || [ -z "$CANARY" ] || {
  echo "choose --only-node or --canary, not both" >&2
  exit 2
}
case "$SSH_USER" in ''|*[!A-Za-z0-9._-]*) echo "invalid SSH user" >&2; exit 2 ;; esac
case "$HOME_TARGET" in ''|*[!A-Za-z0-9@._:-]*) echo "invalid Home target" >&2; exit 2 ;; esac
for node in "$ONLY_NODE" "$CANARY"; do
  case "$node" in *[!A-Za-z0-9._-]*) echo "invalid node selector" >&2; exit 2 ;; esac
done
for value in "$EXPECTED" "$TIMEOUT" "$HANDSHAKE_STALE" "$HANDSHAKE_WAIT"; do
  case "$value" in ''|*[!0-9]*) echo "invalid numeric option" >&2; exit 2 ;; esac
  [ "$value" -gt 0 ] || { echo "numeric options must be positive" >&2; exit 2; }
done

for command in jq ssh scp python3; do
  command -v "$command" >/dev/null || { echo "$command is required" >&2; exit 2; }
done

RUNTIME_FILES=(
  ops/mesh_registry.py
  ops/mesh-apply-peers
  ops/systemd/kolibri-mesh-apply-peers.service
)
for relative in "${RUNTIME_FILES[@]}"; do
  [ -f "$ROOT_DIR/$relative" ] || { echo "missing runtime file: $relative" >&2; exit 2; }
done
grep -Fx 'Before=kolibri-mesh-registry.service' \
  "$ROOT_DIR/ops/systemd/kolibri-mesh-apply-peers.service" >/dev/null || {
  echo "peer apply unit is missing registrar ordering" >&2
  exit 2
}
grep -Fx 'WantedBy=multi-user.target wg-quick@wg-kolibri.service' \
  "$ROOT_DIR/ops/systemd/kolibri-mesh-apply-peers.service" >/dev/null || {
  echo "peer apply unit is missing wg-quick enablement" >&2
  exit 2
}

jq -e --argjson expected "$EXPECTED" '
  (.peers | type == "object") and
  ([.peers[] | .node_id] | length == $expected) and
  ([.peers[] | .node_id] | unique | length == $expected) and
  ([.peers[] | .mesh_ip] | unique | length == $expected) and
  ([.peers[] | .public_key] | unique | length == $expected) and
  (all(.peers[];
    (.node_id | type == "string" and test("^[A-Za-z0-9._-]+$")) and
    (.mesh_ip | type == "string" and test("^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$")) and
    (.public_key | type == "string" and length >= 40)
  )) and
  ([.peers[] | select(.node_id == "home")] | length == 1)
' "$MANIFEST" >/dev/null || { echo "manifest validation failed" >&2; exit 2; }

SELECTED_NODE=${CANARY:-$ONLY_NODE}
if [ -n "$SELECTED_NODE" ]; then
  jq -e --arg node "$SELECTED_NODE" 'any(.peers[]; .node_id == $node)' "$MANIFEST" >/dev/null || {
    echo "selected node is not in manifest" >&2
    exit 2
  }
fi

sha256_file() {
  if command -v sha256sum >/dev/null; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

STAGE=$(mktemp -d "${TMPDIR:-/tmp}/kolibri-mesh-persistence.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT
install -m755 "$ROOT_DIR/ops/mesh_registry.py" "$STAGE/mesh_registry.py"
install -m755 "$ROOT_DIR/ops/mesh-apply-peers" "$STAGE/mesh-apply-peers"
install -m644 "$ROOT_DIR/ops/systemd/kolibri-mesh-apply-peers.service" \
  "$STAGE/kolibri-mesh-apply-peers.service"
install -m600 "$MANIFEST" "$STAGE/peers.json"
for name in mesh_registry.py mesh-apply-peers kolibri-mesh-apply-peers.service peers.json; do
  printf '%s  %s\n' "$(sha256_file "$STAGE/$name")" "$name"
done >"$STAGE/checksums.sha256"
BUNDLE_SHA256=$(sha256_file "$STAGE/checksums.sha256")

jq -r '.peers[] | [.node_id,.mesh_ip] | @tsv' "$MANIFEST" | sort >"$STAGE/nodes.tsv"

SSH_CMD=()
SCP_CMD=()
REMOTE_TARGET=""
PATH_KIND=""

select_transport() {
  local node=$1 ip=$2 target="$SSH_USER@$ip"
  SSH_CMD=() SCP_CMD=() REMOTE_TARGET="" PATH_KIND=""
  if ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" -o ConnectionAttempts=1 \
    "$target" true </dev/null >/dev/null 2>&1; then
    SSH_CMD=(ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" "$target")
    SCP_CMD=(scp -q -o BatchMode=yes -o ConnectTimeout="$TIMEOUT")
    REMOTE_TARGET=$target
    PATH_KIND=direct
    return 0
  fi
  if [ "$node" != home ] && \
    ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" -o ConnectionAttempts=1 \
      -o ProxyJump="$HOME_TARGET" "$target" true </dev/null >/dev/null 2>&1; then
    SSH_CMD=(ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" -o ProxyJump="$HOME_TARGET" "$target")
    SCP_CMD=(scp -q -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" -o ProxyJump="$HOME_TARGET")
    REMOTE_TARGET=$target
    PATH_KIND=home-proxy
    return 0
  fi
  return 1
}

remote_preflight() {
  local node=$1 ip=$2
  "${SSH_CMD[@]}" /bin/bash -s -- "$node" "$ip" "$EXPECTED" "$HANDSHAKE_STALE" <<'REMOTE'
set -euo pipefail
node_id=$1
mesh_ip=$2
expected=$3
stale=$4
[ "$(id -u)" -eq 0 ]
systemctl is-active --quiet wg-quick@wg-kolibri.service
ip -o -4 addr show dev wg-kolibri | awk '{print $4}' | grep -Fx "$mesh_ip/24" >/dev/null || \
  ip -o -4 addr show dev wg-kolibri | awk '{print $4}' | grep -Fx "$mesh_ip/32" >/dev/null
fragments=$(find /etc/wireguard/kolibri-peers.d -maxdepth 1 -type f -name '*.conf' 2>/dev/null | wc -l | tr -d ' ')
[ "$fragments" -ge "$expected" ]
runtime_peers=$(wg show wg-kolibri peers | wc -l | tr -d ' ')
now=$(date +%s)
fresh=$(wg show wg-kolibri latest-handshakes | awk -v now="$now" -v stale="$stale" '$2 > 0 && now-$2 <= stale {n++} END {print n+0}')
unit_load=$(systemctl show kolibri-mesh-apply-peers.service -p LoadState --value 2>/dev/null || true)
unit_enabled=$(systemctl is-enabled kolibri-mesh-apply-peers.service 2>/dev/null || true)
printf 'node=%s mesh_ip=%s fragments=%s expected=%s runtime_peers=%s fresh_handshakes=%s unit_load=%s unit_enabled=%s\n' \
  "$node_id" "$mesh_ip" "$fragments" "$expected" "$runtime_peers" "$fresh" \
  "${unit_load:-missing}" "${unit_enabled:-missing}"
REMOTE
}

rollback_node() {
  local node=$1
  echo "rollback_start node=$node" >&2
  "${SSH_CMD[@]}" /bin/bash -s -- "$RUN_ID" "$node" <<'REMOTE'
set -euo pipefail
run_id=$1
node_id=$2
backup=/var/backups/kolibri/mesh-peer-persistence/$run_id/$node_id
[ -d "$backup" ] || { echo "rollback backup missing" >&2; exit 1; }

previous_enabled=$(cat "$backup/unit.enabled" 2>/dev/null || true)
previous_active=$(cat "$backup/unit.active" 2>/dev/null || true)
systemctl stop kolibri-mesh-apply-peers.service >/dev/null 2>&1 || true

while IFS='|' read -r state path; do
  [ -n "$path" ] || continue
  if [ "$state" = present ]; then
    mkdir -p "$(dirname "$path")"
    cp -a "$backup$path" "$path"
  else
    rm -f "$path"
  fi
done <"$backup/paths.before"

systemctl daemon-reload
case "$previous_enabled" in enabled|enabled-runtime|linked|linked-runtime)
  systemctl enable kolibri-mesh-apply-peers.service >/dev/null 2>&1 || true ;;
*) systemctl disable kolibri-mesh-apply-peers.service >/dev/null 2>&1 || true ;;
esac
if [ "$previous_active" = active ] && systemctl cat kolibri-mesh-apply-peers.service >/dev/null 2>&1; then
  systemctl start kolibri-mesh-apply-peers.service
fi

# The root-only snapshot never leaves the node and is never printed. syncconf
# restores the exact prior peer runtime without cycling the WireGuard link.
if [ -s "$backup/wg.runtime.before.conf" ]; then
  wg syncconf wg-kolibri "$backup/wg.runtime.before.conf"
fi
printf 'rolled_back\n' >"$backup/status"
chmod 0600 "$backup/status"
REMOTE
  echo "rollback_complete node=$node" >&2
}

apply_node() {
  local node=$1 ip=$2 remote_stage="/run/kolibri-mesh-rollout/$RUN_ID"
  "${SSH_CMD[@]}" "install -d -m700 '$remote_stage'"
  "${SCP_CMD[@]}" \
    "$STAGE/mesh_registry.py" \
    "$STAGE/mesh-apply-peers" \
    "$STAGE/kolibri-mesh-apply-peers.service" \
    "$STAGE/peers.json" \
    "$STAGE/checksums.sha256" \
    "$REMOTE_TARGET:$remote_stage/"

  if ! "${SSH_CMD[@]}" /bin/bash -s -- \
      "$RUN_ID" "$node" "$ip" "$EXPECTED" "$HANDSHAKE_STALE" "$HANDSHAKE_WAIT" \
      "$remote_stage" <<'REMOTE'
set -euo pipefail
run_id=$1
node_id=$2
mesh_ip=$3
expected=$4
stale=$5
wait_seconds=$6
stage=$7
backup=/var/backups/kolibri/mesh-peer-persistence/$run_id/$node_id
umask 077

[ "$(id -u)" -eq 0 ]
systemctl is-active --quiet wg-quick@wg-kolibri.service
wg_started_before=$(systemctl show wg-quick@wg-kolibri.service -p ActiveEnterTimestampMonotonic --value)
[ -n "$wg_started_before" ]
cd "$stage"
sha256sum -c checksums.sha256 >/dev/null

install -d -m700 "$backup"
paths='
/usr/local/lib/kolibri/mesh_registry.py
/usr/local/sbin/kolibri-mesh-apply-peers
/etc/systemd/system/kolibri-mesh-apply-peers.service
/var/lib/kolibri-mesh/applied-public-keys'
: >"$backup/paths.before"
for path in $paths; do
  if [ -L "$path" ]; then
    echo "managed path is a symlink: $path" >&2
    exit 31
  fi
  if [ -e "$path" ]; then
    mkdir -p "$backup$(dirname "$path")"
    cp -a "$path" "$backup$path"
    printf 'present|%s\n' "$path" >>"$backup/paths.before"
    sha256sum "$path" >>"$backup/checksums.before"
  else
    printf 'missing|%s\n' "$path" >>"$backup/paths.before"
  fi
done
systemctl is-enabled kolibri-mesh-apply-peers.service >"$backup/unit.enabled" 2>/dev/null || true
systemctl is-active kolibri-mesh-apply-peers.service >"$backup/unit.active" 2>/dev/null || true

# This contains interface private material, so it stays root-only on the same
# node and is used solely for an exact, no-link-restart rollback.
wg showconf wg-kolibri >"$backup/wg.runtime.before.conf"
chmod 0600 "$backup/wg.runtime.before.conf"
printf '%s\n' "$wg_started_before" >"$backup/wg.started.before"
sha256sum "$backup/wg.runtime.before.conf" >"$backup/wg.runtime.before.sha256"

install -d -m755 /usr/local/lib/kolibri /usr/local/sbin
install -m755 "$stage/mesh_registry.py" /usr/local/lib/kolibri/mesh_registry.py
install -m755 "$stage/mesh-apply-peers" /usr/local/sbin/kolibri-mesh-apply-peers
install -m644 "$stage/kolibri-mesh-apply-peers.service" \
  /etc/systemd/system/kolibri-mesh-apply-peers.service
/usr/bin/python3 -m py_compile /usr/local/lib/kolibri/mesh_registry.py
systemctl daemon-reload
systemctl enable kolibri-mesh-apply-peers.service >/dev/null
systemctl restart kolibri-mesh-apply-peers.service
systemctl is-active --quiet kolibri-mesh-apply-peers.service

wg_started_after=$(systemctl show wg-quick@wg-kolibri.service -p ActiveEnterTimestampMonotonic --value)
[ "$wg_started_after" = "$wg_started_before" ] || {
  echo "wg-quick restart detected" >&2
  exit 32
}
sha256sum "$stage/mesh_registry.py" /usr/local/lib/kolibri/mesh_registry.py | awk '{print $1}' | uniq | wc -l | grep -Fx 1 >/dev/null
sha256sum "$stage/mesh-apply-peers" /usr/local/sbin/kolibri-mesh-apply-peers | awk '{print $1}' | uniq | wc -l | grep -Fx 1 >/dev/null
sha256sum "$stage/kolibri-mesh-apply-peers.service" /etc/systemd/system/kolibri-mesh-apply-peers.service | awk '{print $1}' | uniq | wc -l | grep -Fx 1 >/dev/null

deadline=$((SECONDS + wait_seconds))
while :; do
  metrics=$(/usr/bin/python3 - "$stage/peers.json" "$node_id" "$stale" <<'PY'
import json, subprocess, sys, time
manifest_path, node_id, stale_text = sys.argv[1:]
stale = int(stale_text)
payload = json.load(open(manifest_path, encoding="utf-8"))
records = [value for value in payload["peers"].values() if isinstance(value, dict)]
runtime = {}
for line in subprocess.check_output(["wg", "show", "wg-kolibri", "dump"], text=True).splitlines()[1:]:
    fields = line.split("\t")
    runtime[fields[0]] = {"allowed": fields[3].split(","), "handshake": int(fields[4])}
missing = []
home_key = None
for record in records:
    if record.get("node_id") == "home":
        home_key = record.get("public_key")
    if record.get("node_id") == node_id:
        continue
    peer = runtime.get(record.get("public_key"))
    if not peer or f'{record.get("mesh_ip")}/32' not in peer["allowed"]:
        missing.append(record.get("node_id"))
now = int(time.time())
fresh_keys = {key for key, value in runtime.items() if value["handshake"] and now - value["handshake"] <= stale}
home_fresh = node_id == "home" or (home_key in fresh_keys)
print(f'{len(runtime)} {len(missing)} {len(fresh_keys)} {1 if home_fresh else 0}')
PY
  )
  read -r runtime_count missing_count fresh_count home_fresh <<<"$metrics"
  minimum=$((expected - 1))
  if [ "$runtime_count" -ge "$minimum" ] && [ "$missing_count" -eq 0 ] && \
     [ "$fresh_count" -ge 2 ] && [ "$home_fresh" -eq 1 ]; then
    break
  fi
  [ "$SECONDS" -lt "$deadline" ] || {
    echo "peer/handshake convergence gate failed" >&2
    exit 33
  }
  sleep 2
done

printf 'applied\n' >"$backup/status"
printf 'runtime_peers=%s missing_manifest_peers=%s fresh_handshakes=%s home_fresh=%s\n' \
  "$runtime_count" "$missing_count" "$fresh_count" "$home_fresh" >"$backup/verification"
chmod 0600 "$backup/status" "$backup/verification"
rm -rf "$stage"
REMOTE
  then
    rollback_node "$node" || true
    return 1
  fi

  # Controller-side evidence: the node must become directly reachable from
  # the Mac's existing route and remain reachable from Home.  No route or VPN
  # command is used here.
  local deadline=$((SECONDS + HANDSHAKE_WAIT))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" -o ConnectionAttempts=1 \
      "$SSH_USER@$ip" true </dev/null >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "Mac direct SSH gate failed: $node" >&2
    rollback_node "$node" || true
    return 1
  fi

  if [ "$node" = home ]; then
    if ! ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" "$HOME_TARGET" true \
      </dev/null >/dev/null 2>&1; then
      echo "Home self gate failed: $node" >&2
      rollback_node "$node" || true
      return 1
    fi
  elif ! ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" "$HOME_TARGET" \
      ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" -o ConnectionAttempts=1 \
      "$SSH_USER@$ip" true </dev/null >/dev/null 2>&1; then
    echo "Home SSH gate failed: $node" >&2
    rollback_node "$node" || true
    return 1
  fi
  printf 'apply_verified\t%s\t%s\t%s\n' "$node" "$ip" "$PATH_KIND"
}

printf 'run_id=%s mode=%s expected=%s bundle_sha256=%s selector=%s\n' \
  "$RUN_ID" "$([ "$APPLY" = true ] && echo apply || echo dry-run)" "$EXPECTED" \
  "$BUNDLE_SHA256" "${SELECTED_NODE:-all}"

failures=0
selected=0
while IFS=$'\t' read -r node ip; do
  [ -z "$SELECTED_NODE" ] || [ "$node" = "$SELECTED_NODE" ] || continue
  selected=$((selected + 1))
  if ! select_transport "$node" "$ip"; then
    printf 'unreachable\t%s\t%s\n' "$node" "$ip"
    failures=$((failures + 1))
    continue
  fi
  if ! preflight=$(remote_preflight "$node" "$ip"); then
    printf 'preflight_failed\t%s\t%s\t%s\n' "$node" "$ip" "$PATH_KIND"
    failures=$((failures + 1))
    continue
  fi
  printf 'preflight\t%s\t%s\t%s\t%s\n' "$node" "$ip" "$PATH_KIND" "$preflight"
  if [ "$APPLY" = true ] && ! apply_node "$node" "$ip"; then
    printf 'apply_failed\t%s\t%s\t%s\n' "$node" "$ip" "$PATH_KIND"
    failures=$((failures + 1))
    [ -z "$CANARY" ] || break
  fi
done <"$STAGE/nodes.tsv"

[ "$selected" -gt 0 ] || { echo "no selected manifest members" >&2; exit 2; }
[ "$failures" -eq 0 ] || { echo "mesh_persistence_failures=$failures" >&2; exit 1; }
if [ "$APPLY" = true ]; then
  echo "apply_complete"
else
  echo "dry_run_complete"
fi

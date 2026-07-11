#!/usr/bin/env bash
# Guarded recovery for the server whose WireGuard startup is blocked by the
# legacy AllowedIPs claim. The node and external SSH host are resolved
# from the supplied membership manifest; no server address is embedded here.
#
# Default mode is read-only. The conflicting CIDR and current route-owner
# interface are explicit operator inputs; no incident topology is embedded.

set -euo pipefail

MANIFEST="${KOLIBRI_MESH_MEMBERSHIP_MANIFEST:-}"
NODE_ID=""
HOME_TARGET="${KOLIBRI_HOME_SSH_TARGET:-home}"
SSH_USER="${KOLIBRI_FLEET_SSH_USER:-root}"
EXPECTED="${KOLIBRI_EXPECTED_SERVERS:-21}"
TIMEOUT="${KOLIBRI_FLEET_PROBE_TIMEOUT:-6}"
HANDSHAKE_STALE="${KOLIBRI_MESH_HANDSHAKE_STALE_SECONDS:-180}"
HANDSHAKE_WAIT="${KOLIBRI_MESH_HANDSHAKE_WAIT_SECONDS:-45}"
CONFLICT_CIDR=""
ROUTE_OWNER=""
APPLY=false
RUN_ID="mesh-route-collision-$(date -u +%Y%m%dT%H%M%SZ)"

usage() {
  cat >&2 <<'EOF'
usage: repair-mesh-route-collision.sh --manifest FILE --node NODE
       --conflict-cidr CIDR --route-owner INTERFACE
       [--home SSH_TARGET] [--ssh-user USER] [--expect 21] [--apply]

The selected manifest member must be reachable through its manifest endpoint.
Without --apply the command only validates the exact route collision and prints
a plan.  It never changes the active Mac VPN or Home route.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --manifest) MANIFEST=${2:?missing manifest}; shift 2 ;;
    --node) NODE_ID=${2:?missing node}; shift 2 ;;
    --conflict-cidr) CONFLICT_CIDR=${2:?missing conflict CIDR}; shift 2 ;;
    --route-owner) ROUTE_OWNER=${2:?missing route owner}; shift 2 ;;
    --home) HOME_TARGET=${2:?missing Home target}; shift 2 ;;
    --ssh-user) SSH_USER=${2:?missing SSH user}; shift 2 ;;
    --expect) EXPECTED=${2:?missing expected count}; shift 2 ;;
    --apply) APPLY=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
done

[ -f "$MANIFEST" ] || { echo "manifest is required" >&2; exit 2; }
case "$NODE_ID" in ''|*[!A-Za-z0-9._-]*) echo "valid --node is required" >&2; exit 2 ;; esac
case "$SSH_USER" in ''|*[!A-Za-z0-9._-]*) echo "invalid SSH user" >&2; exit 2 ;; esac
case "$HOME_TARGET" in ''|*[!A-Za-z0-9@._:-]*) echo "invalid Home target" >&2; exit 2 ;; esac
case "$ROUTE_OWNER" in ''|*[!A-Za-z0-9_.:@-]*) echo "valid --route-owner is required" >&2; exit 2 ;; esac
python3 - "$CONFLICT_CIDR" <<'PY' || { echo "valid --conflict-cidr is required" >&2; exit 2; }
import ipaddress, sys
network = ipaddress.ip_network(sys.argv[1], strict=True)
raise SystemExit(0 if network.version == 4 and 0 < network.prefixlen <= 32 else 1)
PY
for value in "$EXPECTED" "$TIMEOUT" "$HANDSHAKE_STALE" "$HANDSHAKE_WAIT"; do
  case "$value" in ''|*[!0-9]*) echo "invalid numeric option" >&2; exit 2 ;; esac
  [ "$value" -gt 0 ] || { echo "numeric options must be positive" >&2; exit 2; }
done
for command in jq ssh python3; do
  command -v "$command" >/dev/null || { echo "$command is required" >&2; exit 2; }
done

jq -e --argjson expected "$EXPECTED" --arg node "$NODE_ID" '
  (.peers | type == "object") and
  ([.peers[] | .node_id] | length == $expected) and
  ([.peers[] | .node_id] | unique | length == $expected) and
  ([.peers[] | .mesh_ip] | unique | length == $expected) and
  ([.peers[] | select(.node_id == "home")] | length == 1) and
  ([.peers[] | select(.node_id == $node)] | length == 1)
' "$MANIFEST" >/dev/null || { echo "manifest/node validation failed" >&2; exit 2; }

TARGET_JSON=$(python3 - "$MANIFEST" "$NODE_ID" <<'PY'
import json, re, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
node_id = sys.argv[2]
record = next(value for value in payload["peers"].values() if value.get("node_id") == node_id)
endpoint = str(record.get("endpoint") or "")
match = re.fullmatch(r"([^:\[\]]+):(\d{1,5})", endpoint)
if not match or not 1 <= int(match.group(2)) <= 65535:
    raise SystemExit("manifest endpoint is not a safe host:port")
host = match.group(1)
if not re.fullmatch(r"[A-Za-z0-9.-]+", host):
    raise SystemExit("manifest endpoint host is unsafe")
print(json.dumps({"mesh_ip": record["mesh_ip"], "host": host}, separators=(",", ":")))
PY
)
MESH_IP=$(jq -r '.mesh_ip' <<<"$TARGET_JSON")
EXTERNAL_HOST=$(jq -r '.host' <<<"$TARGET_JSON")

SSH_CMD=()
PATH_KIND=""
if ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" -o ConnectionAttempts=1 \
  "$SSH_USER@$EXTERNAL_HOST" true </dev/null >/dev/null 2>&1; then
  SSH_CMD=(ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" "$SSH_USER@$EXTERNAL_HOST")
  PATH_KIND=external-direct
elif ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" "$HOME_TARGET" \
  ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" -o ConnectionAttempts=1 \
  "$SSH_USER@$EXTERNAL_HOST" true </dev/null >/dev/null 2>&1; then
  SSH_CMD=(ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" "$HOME_TARGET"
    ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" "$SSH_USER@$EXTERNAL_HOST")
  PATH_KIND=home-external-relay
else
  echo "selected node external SSH is unreachable" >&2
  exit 1
fi

preflight=$("${SSH_CMD[@]}" /bin/bash -s -- \
  "$NODE_ID" "$MESH_IP" "$CONFLICT_CIDR" "$ROUTE_OWNER" <<'REMOTE'
set -euo pipefail
node_id=$1
mesh_ip=$2
conflict=$3
owner=$4
config=/etc/wireguard/wg-kolibri.conf
[ "$(id -u)" -eq 0 ]
[ -f "$config" ] && [ ! -L "$config" ]
[ -x /usr/local/sbin/kolibri-mesh-apply-peers ]
[ -f /usr/local/lib/kolibri/mesh_registry.py ]
ip -o link show dev "$owner" | grep -q '<[^>]*UP[^>]*>'
route=$(ip -4 route show table main exact "$conflict")
printf '%s\n' "$route" | grep -Eq "(^| )dev $owner( |$)"
hits=$(python3 - "$config" "$conflict" <<'PY'
import re, sys
text = open(sys.argv[1], encoding="utf-8").read().splitlines()
cidr = sys.argv[2]
hits = 0
for line in text:
    match = re.match(r"^\s*AllowedIPs\s*=\s*(.*)$", line)
    if not match:
        continue
    tokens = [value.strip() for value in match.group(1).split(",") if value.strip()]
    hits += tokens.count(cidr)
    if cidr in tokens and len(tokens) < 2:
        raise SystemExit("conflict token has no safe sibling AllowedIP")
print(hits)
PY
)
[ "$hits" -eq 1 ]
wg_state=$(systemctl is-active wg-quick@wg-kolibri.service 2>/dev/null || true)
wg_result=$(systemctl show wg-quick@wg-kolibri.service -p Result --value 2>/dev/null || true)
printf 'node=%s mesh_ip=%s conflict_hits=%s route_owner=%s route_present=true wg_state=%s wg_result=%s\n' \
  "$node_id" "$mesh_ip" "$hits" "$owner" "${wg_state:-unknown}" "${wg_result:-unknown}"
REMOTE
)

printf 'run_id=%s mode=%s node=%s mesh_ip=%s path=%s %s\n' \
  "$RUN_ID" "$([ "$APPLY" = true ] && echo apply || echo dry-run)" "$NODE_ID" \
  "$MESH_IP" "$PATH_KIND" "$preflight"

if [ "$APPLY" != true ]; then
  echo "dry_run_complete"
  exit 0
fi

rollback_remote() {
  echo "rollback_start node=$NODE_ID" >&2
  "${SSH_CMD[@]}" /bin/bash -s -- "$RUN_ID" "$NODE_ID" "$CONFLICT_CIDR" "$ROUTE_OWNER" <<'REMOTE'
set -euo pipefail
run_id=$1
node_id=$2
conflict=$3
owner=$4
backup=/var/backups/kolibri/mesh-route-collision/$run_id/$node_id
config=/etc/wireguard/wg-kolibri.conf
[ -f "$backup/wg-kolibri.conf" ] || { echo "rollback backup missing" >&2; exit 1; }
systemctl stop wg-quick@wg-kolibri.service >/dev/null 2>&1 || true
install -m600 "$backup/wg-kolibri.conf" "$config"
sha256sum -c "$backup/wg-kolibri.conf.sha256" >/dev/null
ip -o link show dev "$owner" | grep -q '<[^>]*UP[^>]*>'
ip -4 route show table main exact "$conflict" | grep -Eq "(^| )dev $owner( |$)"
printf 'rolled_back\n' >"$backup/status"
chmod 0600 "$backup/status"
REMOTE
  echo "rollback_complete node=$NODE_ID" >&2
}

if ! "${SSH_CMD[@]}" /bin/bash -s -- \
    "$RUN_ID" "$NODE_ID" "$MESH_IP" "$EXPECTED" "$CONFLICT_CIDR" "$ROUTE_OWNER" \
    "$HANDSHAKE_STALE" "$HANDSHAKE_WAIT" <<'REMOTE'
set -euo pipefail
run_id=$1
node_id=$2
mesh_ip=$3
expected=$4
conflict=$5
owner=$6
stale=$7
wait_seconds=$8
config=/etc/wireguard/wg-kolibri.conf
backup=/var/backups/kolibri/mesh-route-collision/$run_id/$node_id
umask 077

[ "$(id -u)" -eq 0 ]
[ -f "$config" ] && [ ! -L "$config" ]
if systemctl is-active --quiet wg-quick@wg-kolibri.service || ip link show dev wg-kolibri >/dev/null 2>&1; then
  echo "wg-kolibri is unexpectedly active; refusing collision repair" >&2
  exit 41
fi
ip -o link show dev "$owner" | grep -q '<[^>]*UP[^>]*>'
ip -4 route show table main exact "$conflict" | grep -Eq "(^| )dev $owner( |$)"
[ ! -e "$backup" ] || { echo "backup already exists" >&2; exit 42; }
install -d -m700 "$backup"
cp -a "$config" "$backup/wg-kolibri.conf"
chmod 0600 "$backup/wg-kolibri.conf"
(cd "$backup" && sha256sum wg-kolibri.conf >wg-kolibri.conf.sha256)
systemctl show wg-quick@wg-kolibri.service -p ActiveState -p Result \
  >"$backup/wg-unit.before"
ip -4 route show table main exact "$conflict" >"$backup/route.before"

python3 - "$config" "$conflict" <<'PY'
import os, re, stat, sys, tempfile
from pathlib import Path

path = Path(sys.argv[1])
cidr = sys.argv[2]
metadata = path.lstat()
if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
    raise SystemExit("unsafe WireGuard config type")
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
removed = 0
result = []
for line in lines:
    match = re.match(r"^(\s*AllowedIPs\s*=\s*)(.*?)(\r?\n)?$", line)
    if not match:
        result.append(line)
        continue
    tokens = [value.strip() for value in match.group(2).split(",") if value.strip()]
    count = tokens.count(cidr)
    if count:
        removed += count
        tokens = [value for value in tokens if value != cidr]
        if not tokens:
            raise SystemExit("refusing to leave an empty AllowedIPs line")
        line = f'{match.group(1)}{", ".join(tokens)}{match.group(3) or ""}'
    result.append(line)
if removed != 1:
    raise SystemExit("expected exactly one conflict token")
fd, temporary = tempfile.mkstemp(prefix=".wg-kolibri.", dir=str(path.parent))
try:
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.writelines(result)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, stat.S_IMODE(metadata.st_mode))
    os.chown(temporary, metadata.st_uid, metadata.st_gid)
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY

wg-quick strip wg-kolibri >/dev/null
ip -o link show dev "$owner" | grep -q '<[^>]*UP[^>]*>'
ip -4 route show table main exact "$conflict" | grep -Eq "(^| )dev $owner( |$)"
systemctl reset-failed wg-quick@wg-kolibri.service || true
systemctl start wg-quick@wg-kolibri.service
systemctl is-active --quiet wg-quick@wg-kolibri.service
ip -o -4 addr show dev wg-kolibri | awk '{print $4}' | grep -Eq "^${mesh_ip}/(24|32)$"
ip -4 route show table main exact "$conflict" | grep -Eq "(^| )dev $owner( |$)"

# wg-quick starts from the minimal static base. Apply the already-replicated
# fragments before the recovery gate; the normal persistence rollout then
# installs and enables the boot unit on this node.
/usr/local/sbin/kolibri-mesh-apply-peers

deadline=$((SECONDS + wait_seconds))
while :; do
  metrics=$(python3 - "$node_id" "$stale" <<'PY'
import json, subprocess, sys, time
node_id, stale_text = sys.argv[1:]
payload = json.load(open("/var/lib/kolibri-mesh/peers.json", encoding="utf-8"))
home = next(value for value in payload["peers"].values() if value.get("node_id") == "home")
rows = subprocess.check_output(["wg", "show", "wg-kolibri", "dump"], text=True).splitlines()[1:]
runtime = {row.split("\t")[0]: row.split("\t") for row in rows}
handshake = int(runtime.get(home["public_key"], ["", "", "", "", "0"])[4])
fresh = bool(handshake and int(time.time()) - handshake <= int(stale_text))
print(f'{len(runtime)} {1 if fresh else 0}')
PY
  )
  read -r runtime_peers home_fresh <<<"$metrics"
  if [ "$runtime_peers" -ge $((expected - 1)) ] && [ "$home_fresh" -eq 1 ]; then
    break
  fi
  [ "$SECONDS" -lt "$deadline" ] || {
    echo "WireGuard recovery handshake gate failed" >&2
    exit 43
  }
  sleep 2
done
printf 'applied\n' >"$backup/status"
printf 'runtime_peers=%s home_fresh=%s route_owner=%s\n' \
  "$runtime_peers" "$home_fresh" "$owner" >"$backup/verification"
chmod 0600 "$backup/status" "$backup/verification"
REMOTE
then
  rollback_remote || true
  exit 1
fi

# The repaired mesh address must be reachable from both the current Mac route
# and Home before this guarded change is accepted.
deadline=$((SECONDS + HANDSHAKE_WAIT))
while [ "$SECONDS" -lt "$deadline" ]; do
  if ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" -o ConnectionAttempts=1 \
    "$SSH_USER@$MESH_IP" true </dev/null >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
if [ "$SECONDS" -ge "$deadline" ]; then
  echo "Mac mesh SSH recovery gate failed" >&2
  rollback_remote || true
  exit 1
fi
if ! ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" "$HOME_TARGET" \
    ssh -o BatchMode=yes -o ConnectTimeout="$TIMEOUT" -o ConnectionAttempts=1 \
    "$SSH_USER@$MESH_IP" true </dev/null >/dev/null 2>&1; then
  echo "Home mesh SSH recovery gate failed" >&2
  rollback_remote || true
  exit 1
fi

printf 'apply_verified\t%s\t%s\t%s\n' "$NODE_ID" "$MESH_IP" "$PATH_KIND"

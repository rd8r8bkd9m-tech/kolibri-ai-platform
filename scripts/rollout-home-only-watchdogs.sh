#!/usr/bin/env bash
# Converge Home-only watchdog and Telegram singleton policy from the replicated
# mesh manifest. Operator transport is SSH; normal factory execution remains API-only.

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MANIFEST=""
HOME_TARGET=""
EXPECTED=21
APPLY=false
RUN_ID="home-singletons-$(date -u +%Y%m%dT%H%M%SZ)"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --manifest) MANIFEST=${2:?missing manifest}; shift 2 ;;
    --home-root) HOME_TARGET=${2:?missing Home target}; shift 2 ;;
    --expect) EXPECTED=${2:?missing expected count}; shift 2 ;;
    --apply) APPLY=true; shift ;;
    -h|--help)
      echo "usage: $0 --manifest FILE [--home-root TARGET] [--expect 21] [--apply]" >&2
      exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[ -f "$MANIFEST" ] || { echo "manifest is required" >&2; exit 2; }
for file in \
  ops/factory_lease_watchdog.py \
  ops/control_plane_endpoint.py \
  ops/systemd/kolibri-factory-lease-watchdog.service \
  ops/systemd/kolibri-factory-lease-watchdog.timer \
  ops/systemd/kolibri-telegram-gateway.service; do
  [ -f "$ROOT_DIR/$file" ] || { echo "missing file: $file" >&2; exit 2; }
done

jq -e --argjson expected "$EXPECTED" '
  (.peers | type == "object") and
  ([.peers[] | .node_id] | length == $expected) and
  ([.peers[] | .node_id] | unique | length == $expected) and
  ([.peers[] | .mesh_ip] | unique | length == $expected) and
  ([.peers[] | select(.node_id == "home")] | length == 1)
' "$MANIFEST" >/dev/null || { echo "manifest validation failed" >&2; exit 2; }
if [ -z "$HOME_TARGET" ]; then
  HOME_IP=$(jq -er '[.peers[] | select(.node_id == "home") | .mesh_ip] | select(length == 1) | .[0]' "$MANIFEST")
  HOME_TARGET="root@$HOME_IP"
fi

STAGE=$(mktemp -d "${TMPDIR:-/tmp}/kolibri-home-singletons.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT
cp "$ROOT_DIR/ops/factory_lease_watchdog.py" "$STAGE/kolibri-factory-lease-watchdog"
cp "$ROOT_DIR/ops/control_plane_endpoint.py" "$STAGE/control_plane_endpoint.py"
cp "$ROOT_DIR/ops/systemd/kolibri-factory-lease-watchdog.service" "$STAGE/kolibri-factory-lease-watchdog.service"
cp "$ROOT_DIR/ops/systemd/kolibri-factory-lease-watchdog.timer" "$STAGE/kolibri-factory-lease-watchdog.timer"
cp "$ROOT_DIR/ops/systemd/kolibri-telegram-gateway.service" "$STAGE/kolibri-telegram-gateway.service"
jq -r '.peers[] | [.node_id,.mesh_ip] | @tsv' "$MANIFEST" | sort >"$STAGE/nodes.tsv"

SSH_CMD=()
SCP_CMD=()
PATH_KIND=""

select_path() {
  local node=$1 ip=$2
  SSH_CMD=() SCP_CMD=() PATH_KIND=""
  if [ "$node" = home ]; then
    SSH_CMD=(ssh -o BatchMode=yes "$HOME_TARGET")
    SCP_CMD=(scp -q)
    PATH_KIND=home-root
    return 0
  fi
  if ssh -o BatchMode=yes -o ConnectTimeout=4 -o ConnectionAttempts=1 "root@$ip" true </dev/null >/dev/null 2>&1; then
    SSH_CMD=(ssh -o BatchMode=yes "root@$ip")
    SCP_CMD=(scp -q)
    PATH_KIND=direct
    return 0
  fi
  if ssh -o BatchMode=yes -o ConnectTimeout=4 -o ConnectionAttempts=1 -o ProxyJump="$HOME_TARGET" "root@$ip" true </dev/null >/dev/null 2>&1; then
    SSH_CMD=(ssh -o BatchMode=yes -o ProxyJump="$HOME_TARGET" "root@$ip")
    SCP_CMD=(scp -q -o ProxyJump="$HOME_TARGET")
    PATH_KIND=home-proxy
    return 0
  fi
  return 1
}

copy_bundle() {
  local node=$1 ip=$2 remote=/tmp/$RUN_ID
  if [ "$node" = home ]; then
    "${SSH_CMD[@]}" "install -d -m700 '$remote'"
    "${SCP_CMD[@]}" "$STAGE"/kolibri-* "$STAGE/control_plane_endpoint.py" "$HOME_TARGET:$remote/"
  else
    "${SSH_CMD[@]}" "install -d -m700 '$remote'"
    "${SCP_CMD[@]}" "$STAGE"/kolibri-* "$STAGE/control_plane_endpoint.py" "root@$ip:$remote/"
  fi
}

apply_node() {
  local node=$1 ip=$2 remote=/tmp/$RUN_ID
  copy_bundle "$node" "$ip"
  "${SSH_CMD[@]}" /bin/bash -s -- "$RUN_ID" "$node" <<'REMOTE'
set -euo pipefail
run_id=$1
node=$2
stage=/tmp/$run_id
backup=/var/backups/kolibri/$run_id
install -d -m700 "$backup"
install -d -m755 /usr/local/lib/kolibri
for path in \
  /usr/local/bin/kolibri-factory-lease-watchdog \
  /usr/local/lib/kolibri/control_plane_endpoint.py \
  /etc/systemd/system/kolibri-factory-lease-watchdog.service \
  /etc/systemd/system/kolibri-factory-lease-watchdog.timer \
  /etc/systemd/system/kolibri-factory-lease-watchdog.service.d \
  /etc/systemd/system/kolibri-telegram-gateway.service \
  /etc/systemd/system/kolibri-telegram-gateway.service.d; do
  if [ -e "$path" ]; then
    mkdir -p "$backup$(dirname "$path")"
    cp -a "$path" "$backup$path"
  fi
done

rm -rf /etc/systemd/system/kolibri-factory-lease-watchdog.service.d
install -o root -g root -m755 "$stage/kolibri-factory-lease-watchdog" /usr/local/bin/kolibri-factory-lease-watchdog
install -o root -g root -m644 "$stage/control_plane_endpoint.py" /usr/local/lib/kolibri/control_plane_endpoint.py
install -o root -g root -m644 "$stage/kolibri-factory-lease-watchdog.service" /etc/systemd/system/kolibri-factory-lease-watchdog.service
install -o root -g root -m644 "$stage/kolibri-factory-lease-watchdog.timer" /etc/systemd/system/kolibri-factory-lease-watchdog.timer
install -o root -g root -m644 "$stage/kolibri-telegram-gateway.service" /etc/systemd/system/kolibri-telegram-gateway.service
python3 -m py_compile /usr/local/bin/kolibri-factory-lease-watchdog /usr/local/lib/kolibri/control_plane_endpoint.py
systemctl daemon-reload

# Polling is intentionally paused fleet-wide until the Home gateway passes the
# single-consumer checkpoint gate. This stops duplicate replies immediately.
systemctl disable --now kolibri-telegram-gateway.service 2>/dev/null || true
systemctl stop kolibri-telegram-gateway.service 2>/dev/null || true
if [ "$node" != home ]; then
  # A locally installed /etc unit cannot be masked until the regular file is
  # removed. It has already been copied into the per-run rollback backup.
  for unit in \
    kolibri-telegram-gateway.service \
    kolibri-factory-lease-watchdog.service \
    kolibri-factory-lease-watchdog.timer; do
    fragment=$(systemctl show "$unit" -p FragmentPath --value 2>/dev/null || true)
    if [ "$fragment" = "/etc/systemd/system/$unit" ] && [ ! -L "$fragment" ]; then
      rm -f "$fragment"
    fi
    systemctl mask --now "$unit" >/dev/null 2>&1 || true
  done
else
  systemctl unmask kolibri-telegram-gateway.service 2>/dev/null || true
fi

systemctl daemon-reload
if [ "$node" = home ]; then
  systemctl enable --now kolibri-factory-lease-watchdog.timer
  systemctl reset-failed kolibri-factory-lease-watchdog.service || true
  systemctl start kolibri-factory-lease-watchdog.service
  systemctl show kolibri-factory-lease-watchdog.service -p Result --value | grep -Fx success >/dev/null
else
  systemctl reset-failed kolibri-factory-lease-watchdog.service 2>/dev/null || true
fi
rm -rf "$stage"
REMOTE
}

audit_node() {
  local node=$1 ip=$2
  "${SSH_CMD[@]}" /bin/bash -s -- "$node" "$PATH_KIND" <<'REMOTE'
set -euo pipefail
node=$1
path_kind=$2
watchdog_enabled=$(systemctl is-enabled kolibri-factory-lease-watchdog.timer 2>/dev/null || true)
watchdog_active=$(systemctl is-active kolibri-factory-lease-watchdog.timer 2>/dev/null || true)
gateway_enabled=$(systemctl is-enabled kolibri-telegram-gateway.service 2>/dev/null || true)
gateway_active=$(systemctl is-active kolibri-telegram-gateway.service 2>/dev/null || true)
gateway_rows=$(pgrep -af '/usr/local/bin/kolibri-telegram-gateway|telegram_gateway.py' 2>/dev/null || true)
gateway_processes=$(printf '%s\n' "$gateway_rows" | awk '!/pgrep -af/ && NF {n++} END {print n+0}')
legacy_files=$(grep -RIl --exclude='*.bak*' --exclude='*.env' '10\.99\.0\.2:9101\|KOLIBRI_FACTORY_CONTROL_URLS=.*,' \
  /etc/systemd/system/kolibri-factory-lease-watchdog.service \
  /etc/systemd/system/kolibri-factory-lease-watchdog.service.d \
  /usr/local/bin/kolibri-factory-lease-watchdog 2>/dev/null || true)
legacy_hits=$(printf '%s\n' "$legacy_files" | awk 'NF {n++} END {print n+0}')
printf 'audit\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
  "$node" "$path_kind" "${watchdog_enabled:-missing}" "${watchdog_active:-inactive}" \
  "${gateway_enabled:-missing}" "${gateway_active:-inactive}" "$gateway_processes" "$legacy_hits"
REMOTE
}

failed=0
mapfile -t fleet_rows <"$STAGE/nodes.tsv"
# Defer currently unreachable nodes so one host cannot prevent convergence of
# the rest of the dynamic fleet. No hostname or address is special-cased.
ordered_rows=()
deferred_rows=()
for fleet_row in "${fleet_rows[@]}"; do
  IFS=$'\t' read -r probe_node probe_ip <<<"$fleet_row"
  if [ "$probe_node" = home ] || \
     ssh -o BatchMode=yes -o ConnectTimeout=2 -o ConnectionAttempts=1 "root@$probe_ip" true </dev/null >/dev/null 2>&1 || \
     ssh -o BatchMode=yes -o ConnectTimeout=2 -o ConnectionAttempts=1 -o ProxyJump="$HOME_TARGET" "root@$probe_ip" true </dev/null >/dev/null 2>&1; then
    ordered_rows+=("$fleet_row")
  else
    deferred_rows+=("$fleet_row")
  fi
done
ordered_rows+=("${deferred_rows[@]}")
for fleet_row in "${ordered_rows[@]}"; do
  IFS=$'\t' read -r node ip <<<"$fleet_row"
  if ! select_path "$node" "$ip"; then
    printf 'unreachable\t%s\t%s\n' "$node" "$ip"
    failed=$((failed + 1))
    continue
  fi
  if [ "$APPLY" = true ]; then
    if ! apply_node "$node" "$ip"; then
      printf 'apply_failed\t%s\t%s\t%s\n' "$node" "$ip" "$PATH_KIND"
      failed=$((failed + 1))
      continue
    fi
  fi
  audit_node "$node" "$ip" || failed=$((failed + 1))
done

[ "$failed" -eq 0 ] || { echo "fleet_singleton_failures=$failed" >&2; exit 1; }

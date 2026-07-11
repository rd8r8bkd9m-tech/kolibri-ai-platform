#!/usr/bin/env bash
# Install one immutable, service-user-readable MiMoCode runtime on dynamic fleet.

set -euo pipefail

MANIFEST=""
VERSION=0.1.4
EXPECTED=21
PARALLEL=4
APPLY=false
EXCLUDE=""
RUN_ID="mimo-runtime-$(date -u +%Y%m%dT%H%M%SZ)"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --manifest) MANIFEST=${2:?missing manifest}; shift 2 ;;
    --version) VERSION=${2:?missing version}; shift 2 ;;
    --expect) EXPECTED=${2:?missing count}; shift 2 ;;
    --parallel) PARALLEL=${2:?missing parallelism}; shift 2 ;;
    --exclude) EXCLUDE=${2:?missing node}; shift 2 ;;
    --apply) APPLY=true; shift ;;
    *) echo "usage: $0 --manifest FILE [--version 0.1.4] [--exclude NODE] --apply" >&2; exit 2 ;;
  esac
done

[ -f "$MANIFEST" ] || { echo "manifest is required" >&2; exit 2; }
case "$VERSION" in *[!0-9A-Za-z._-]*|'') echo "invalid version" >&2; exit 2 ;; esac
for value in "$EXPECTED" "$PARALLEL"; do case "$value" in *[!0-9]*|'') exit 2 ;; esac; done
case "$EXCLUDE" in *[!A-Za-z0-9._-]*) exit 2 ;; esac
jq -e --argjson expected "$EXPECTED" '(.peers|type=="object") and ([.peers[]]|length==$expected)' "$MANIFEST" >/dev/null

nodes=$(mktemp)
results=$(mktemp -d)
trap 'rm -f "$nodes"; rm -rf "$results"' EXIT
jq -r '.peers[] | [.node_id,.mesh_ip] | @tsv' "$MANIFEST" | sort >"$nodes"

install_node() {
  local node=$1 ip=$2
  local result="$results/${node//[^A-Za-z0-9._-]/_}"
  if [ "$node" = "$EXCLUDE" ]; then
    printf 'excluded\t%s\n' "$node" >"$result"
    return
  fi
  if [ "$APPLY" != true ]; then
    ssh -o BatchMode=yes -o ConnectTimeout=6 "root@$ip" true </dev/null
    printf 'preflight_ok\t%s\n' "$node" >"$result"
    return
  fi
  if ssh "root@$ip" /bin/bash -s -- "$VERSION" "$RUN_ID" <<'REMOTE'
set -euo pipefail
version=$1
run_id=$2
release=/opt/kolibri-runners/mimo-$version
backup=/var/backups/kolibri/$run_id
install -d -m700 "$backup"
if [ -e /usr/local/bin/mimo ] || [ -L /usr/local/bin/mimo ]; then
  cp -a /usr/local/bin/mimo "$backup/mimo.link"
fi
  if [ ! -x "$release/bin/mimo" ] || [ ! -x "$release/bin/.mimocode" ]; then
    rm -rf "$release.tmp"
    install -d -m755 "$release.tmp"
    npm install --prefix "$release.tmp" --omit=dev --no-audit --no-fund "@mimo-ai/cli@$version" >/tmp/kolibri-mimo-install.log 2>&1
    package_root="$release.tmp/node_modules/@mimo-ai"
    variant=mimocode-linux-x64
    if ! grep -qw avx2 /proc/cpuinfo; then
      variant=mimocode-linux-x64-baseline
    fi
    if ldd --version 2>&1 | grep -qi musl; then
      variant="$variant-musl"
    fi
    test -x "$package_root/cli/bin/mimo"
    test -x "$package_root/$variant/bin/mimo"
    runtime="$release.runtime"
    rm -rf "$runtime"
    install -d -m755 "$runtime/bin"
    install -m755 "$package_root/cli/bin/mimo" "$runtime/bin/mimo"
    install -m755 "$package_root/$variant/bin/mimo" "$runtime/bin/.mimocode"
    rm -rf "$release.tmp"
    rm -rf "$release"
    mv "$runtime" "$release"
  fi
chown -R root:root "$release"
chmod -R a+rX,go-w "$release"
ln -sfn "$release/bin/mimo" /usr/local/bin/mimo
sudo -u kolibri-agent env HOME=/var/lib/kolibri-agent /usr/local/bin/mimo --version | grep -Fx "$version" >/dev/null
systemctl restart kolibri-agent-host.service
sleep 5
systemctl is-active --quiet kolibri-agent-host.service
REMOTE
  then
    printf 'installed\t%s\n' "$node" >"$result"
  else
    printf 'failed\t%s\n' "$node" >"$result"
    return 1
  fi
}

running=0
while IFS=$'\t' read -r node ip; do
  install_node "$node" "$ip" &
  running=$((running + 1))
  if [ "$running" -ge "$PARALLEL" ]; then
    wait -n || true
    running=$((running - 1))
  fi
done <"$nodes"
wait || true

cat "$results"/* | sort -k2
failed=$(awk '$1=="failed"{count++} END{print count+0}' "$results"/*)
[ "$failed" -eq 0 ]

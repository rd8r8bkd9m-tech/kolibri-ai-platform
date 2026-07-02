#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-}"

usage() {
  echo "usage: CONTROL_PLANE_URL=http://host:9101 $0 [--repo-root PATH] [--] canary-command [args...]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root)
      ROOT="$2"
      shift 2
      ;;
    --control-plane-url)
      CONTROL_PLANE_URL="$2"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    -*)
      usage
      exit 2
      ;;
    *)
      break
      ;;
  esac
done

if [[ -z "${CONTROL_PLANE_URL}" ]]; then
  usage
  exit 2
fi

python3 "${ROOT}/scripts/verify-control-plane-deployed-sha.py" \
  --repo-root "${ROOT}" \
  --control-plane-url "${CONTROL_PLANE_URL}"

if [[ $# -eq 0 ]]; then
  echo "control_plane_deployed_sha_gate=ok"
  exit 0
fi

exec "$@"

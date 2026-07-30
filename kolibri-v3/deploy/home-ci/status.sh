#!/usr/bin/env bash
set -Eeuo pipefail

target="${1:-home}"
ssh -o BatchMode=yes "${target}" '
  set -eu
  state="$HOME/.local/state/kolibri-v3-home-ci"
  if [ -f "$state/latest-status.env" ]; then
    cat "$state/latest-status.env"
  elif [ -f "$state/latest-run" ]; then
    printf "home_ci_status=running\n"
    printf "home_ci_run_id=%s\n" "$(cat "$state/latest-run")"
  else
    printf "home_ci_status=idle\n"
  fi
  systemctl --user --no-pager --full status \
    kolibri-v3-home-ci.path 2>/dev/null |
    sed -n "1,12p" || true
'


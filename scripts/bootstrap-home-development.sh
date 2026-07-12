#!/usr/bin/env bash
# Prepare the canonical Home development layout. Dry-run is the default.
# This script does not deploy or restart production services.

set -euo pipefail

MODE=dry-run
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
REQUIRED_NODE_VERSION=$(tr -d '[:space:]' < "$REPOSITORY_ROOT/.node-version")
REQUIRED_PYTHON_VERSION=$(tr -d '[:space:]' < "$REPOSITORY_ROOT/.python-version")
HOME_ROOT=${KOLIBRI_HOME_SOURCE_ROOT:-/home/ladik/src}
REPOSITORY_URL=${KOLIBRI_REPOSITORY_URL:-https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform.git}
INTEGRATION_BRANCH=${KOLIBRI_INTEGRATION_BRANCH:-codex/kolibri-ai-os-foundation-20260712}
APPROVAL_ID=${KOLIBRI_OWNER_APPROVAL_ID:-}

usage() {
  cat <<'USAGE'
usage: scripts/bootstrap-home-development.sh [--dry-run | --apply]

Environment:
  KOLIBRI_HOME_SOURCE_ROOT   target root (default /home/ladik/src)
  KOLIBRI_REPOSITORY_URL     canonical Git remote
  KOLIBRI_INTEGRATION_BRANCH branch checked out by the control worktree
  KOLIBRI_OWNER_APPROVAL_ID  required for --apply
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) MODE=dry-run; shift ;;
    --apply) MODE=apply; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

case "$HOME_ROOT" in
  /home/*/src|/srv/kolibri-development) ;;
  *) echo "refusing unsafe Home source root" >&2; exit 2 ;;
esac

case "$INTEGRATION_BRANCH" in
  codex/*) ;;
  *) echo "integration branch must use the codex/ namespace" >&2; exit 2 ;;
esac

MIRROR="$HOME_ROOT/mirrors/kolibri-ai-platform.git"
WORKTREE_ROOT="$HOME_ROOT/kolibri-ai-platform"
CONTROL="$WORKTREE_ROOT/control"
TASKS="$WORKTREE_ROOT/tasks"
RELEASES="$WORKTREE_ROOT/releases"

run() {
  if [ "$MODE" = dry-run ]; then
    printf 'DRY-RUN:'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

verify_runtime_versions() {
  command -v node >/dev/null || {
    echo "Node.js $REQUIRED_NODE_VERSION is required" >&2
    return 2
  }
  command -v python3 >/dev/null || {
    echo "Python $REQUIRED_PYTHON_VERSION is required" >&2
    return 2
  }

  local actual_node actual_python
  actual_node=$(node --version)
  actual_node=${actual_node#v}
  actual_python=$(python3 -c 'import platform; print(platform.python_version())')

  [ "$actual_node" = "$REQUIRED_NODE_VERSION" ] || {
    echo "Home Node.js version mismatch: required $REQUIRED_NODE_VERSION, found $actual_node" >&2
    return 6
  }
  [ "$actual_python" = "$REQUIRED_PYTHON_VERSION" ] || {
    echo "Home Python version mismatch: required $REQUIRED_PYTHON_VERSION, found $actual_python" >&2
    return 6
  }
}

if [ "$MODE" = apply ]; then
  [ -n "$APPROVAL_ID" ] || {
    echo "KOLIBRI_OWNER_APPROVAL_ID is required for --apply" >&2
    exit 3
  }
  command -v git >/dev/null || { echo "git is required" >&2; exit 2; }
  verify_runtime_versions
fi

run mkdir -p "$HOME_ROOT/mirrors" "$WORKTREE_ROOT" "$TASKS" "$RELEASES"

if [ -d "$MIRROR" ]; then
  run git -C "$MIRROR" fetch origin --prune-tags
else
  run git clone --mirror "$REPOSITORY_URL" "$MIRROR"
fi

if [ -e "$CONTROL/.git" ]; then
  if [ "$MODE" = apply ]; then
    [ -z "$(git -C "$CONTROL" status --porcelain=v1 -uall)" ] || {
      echo "existing Home control worktree is dirty; refusing branch switch" >&2
      exit 5
    }
    CURRENT_BRANCH=$(git -C "$CONTROL" branch --show-current)
    if [ "$CURRENT_BRANCH" != "$INTEGRATION_BRANCH" ]; then
      run git -C "$CONTROL" switch "$INTEGRATION_BRANCH"
    fi
  else
    run git -C "$CONTROL" status --short --branch
    printf 'DRY-RUN: verify clean control worktree and switch to %q when needed\n' "$INTEGRATION_BRANCH"
  fi
  run git -C "$CONTROL" status --short --branch
elif [ -e "$CONTROL" ] && [ -n "$(find "$CONTROL" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
  echo "control path exists and is not an empty worktree" >&2
  exit 4
else
  run git --git-dir="$MIRROR" worktree add "$CONTROL" "$INTEGRATION_BRANCH"
fi

cat <<EOF
home_development_layout=$MODE
mirror=$MIRROR
control=$CONTROL
tasks=$TASKS
releases=$RELEASES
branch=$INTEGRATION_BRANCH
required_node=$REQUIRED_NODE_VERSION
required_python=$REQUIRED_PYTHON_VERSION
production_services_changed=false
EOF

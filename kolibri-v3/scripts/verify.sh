#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

mode="${1:---quick}"
case "$mode" in
  --quick | --full) ;;
  *)
    echo "usage: scripts/verify.sh [--quick|--full]" >&2
    exit 64
    ;;
esac

python_bin="backend/venv/bin/python"
ruff_bin="backend/venv/bin/ruff"

require_executable() {
  if [[ ! -x "$1" ]]; then
    echo "required executable is missing: $1" >&2
    exit 1
  fi
}

run() {
  printf '\n==> %s\n' "$*"
  "$@"
}

require_executable "$python_bin"
require_executable "$ruff_bin"

run npm run verify:structure
run "$ruff_bin" check backend server
run "$python_bin" -m compileall -q backend/app server
run env PYTHONPATH=backend "$python_bin" -m pytest -q backend/tests
run npm run typecheck
run npm test

for manifest in packages/*/Cargo.toml; do
  run cargo fmt --manifest-path "$manifest" --check
  run cargo clippy --manifest-path "$manifest" --all-targets -- -D warnings
  run cargo test --manifest-path "$manifest"
done

if [[ "$mode" == "--full" ]]; then
  run npm run build
  run npm --prefix apps/kolibri-mobile run typecheck
  run npm --prefix apps/kolibri-mobile test
  run npm --prefix apps/kolibri-mobile run lint
fi

printf '\nAll %s verification gates passed.\n' "${mode#--}"

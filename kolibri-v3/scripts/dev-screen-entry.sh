#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
v3_root="$(cd -- "${script_dir}/.." && pwd -P)"
runtime_log="${v3_root}/var/dev-runtime/screen.log"
npm_bin="${KOLIBRI_V3_NPM_BIN:-/opt/homebrew/bin/npm}"

[[ -x "${npm_bin}" ]] || {
  printf 'npm is not executable: %s\n' "${npm_bin}" >&2
  exit 1
}

cd -- "${v3_root}"
mkdir -p -- "$(dirname -- "${runtime_log}")"
exec "${npm_bin}" run dev >>"${runtime_log}" 2>&1

#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
project_root="$(cd -- "${script_dir}/../.." && pwd -P)"
repo_root="$(git -C "${project_root}" rev-parse --show-toplevel)"
target="${1:-home}"
revision="${2:-HEAD}"
commit="$(git -C "${repo_root}" rev-parse --verify "${revision}^{commit}")"

[[ "${commit}" =~ ^[0-9a-f]{40}$ ]] || {
  printf '%s\n' 'home_ci_submit_error=commit_invalid' >&2
  exit 2
}
remote_home="$(ssh -o BatchMode=yes "${target}" 'printf %s "$HOME"')"
[[ "${remote_home}" = /* ]] || {
  printf '%s\n' 'home_ci_submit_error=remote_home_invalid' >&2
  exit 2
}
remote_repo="${remote_home}/.local/share/kolibri-v3-home-ci/repository.git"
git -C "${repo_root}" push \
  "${target}:${remote_repo}" \
  "${commit}:refs/heads/candidate"
printf 'home_ci_submit=ok\n'
printf 'home_ci_commit=%s\n' "${commit}"
printf 'home_ci_target=%s\n' "${target}"


#!/usr/bin/env bash
set -Eeuo pipefail

ci_root="${KOLIBRI_HOME_CI_ROOT:-${HOME}/.local/share/kolibri-v3-home-ci}"
state_root="${KOLIBRI_HOME_CI_STATE:-${HOME}/.local/state/kolibri-v3-home-ci}"
bare_repo="${ci_root}/repository.git"
queue_file="${state_root}/queue"
active_file="${state_root}/active"
runs_root="${state_root}/runs"

mkdir -p "${runs_root}"
chmod 0700 "${state_root}" "${runs_root}"
[[ -d "${bare_repo}" && ! -L "${bare_repo}" ]] || {
  printf '%s\n' 'home_ci_runner_error=repository_missing' >&2
  exit 2
}

exec 9>"${state_root}/runner.lock"
flock -n 9 || exit 0
[[ -s "${queue_file}" && ! -L "${queue_file}" ]] || exit 0
mv -f "${queue_file}" "${active_file}"
commit="$(tr -d '[:space:]' < "${active_file}")"
[[ "${commit}" =~ ^[0-9a-f]{40}$ ]] || {
  printf '%s\n' 'home_ci_runner_error=queued_commit_invalid' >&2
  exit 2
}
git --git-dir="${bare_repo}" cat-file -e "${commit}^{commit}" || {
  printf '%s\n' 'home_ci_runner_error=queued_commit_missing' >&2
  exit 2
}

started_at="$(date -u +%Y%m%dT%H%M%SZ)"
run_id="${started_at}-${commit:0:12}"
run_root="${runs_root}/${run_id}"
worktree="${run_root}/worktree"
evidence="${run_root}/evidence"
mkdir -m 0700 "${run_root}" "${evidence}"
printf '%s\n' "${run_id}" > "${state_root}/latest-run"

status="failed"
exit_code=1
run_job() {
  printf 'home_ci_run_id=%s\n' "${run_id}"
  printf 'home_ci_commit=%s\n' "${commit}"
  printf 'home_ci_started_at=%s\n' "${started_at}"
  git clone --no-local --no-checkout "${bare_repo}" "${worktree}"
  git -C "${worktree}" checkout --detach "${commit}"
  [[ "$(git -C "${worktree}" rev-parse HEAD)" == "${commit}" ]]
  [[ -z "$(git -C "${worktree}" status --porcelain --untracked-files=all)" ]]
  nice -n 10 ionice -c 2 -n 7 \
    "${worktree}/kolibri-v3/deploy/home-ci/run-gate.sh" "${evidence}"
}
if run_job > >(tee "${run_root}/run.log") 2>&1; then
  status="passed"
  exit_code=0
else
  exit_code=$?
fi

finished_at="$(date -u +%Y%m%dT%H%M%SZ)"
{
  printf 'home_ci_run_id=%s\n' "${run_id}"
  printf 'home_ci_commit=%s\n' "${commit}"
  printf 'home_ci_status=%s\n' "${status}"
  printf 'home_ci_exit_code=%s\n' "${exit_code}"
  printf 'home_ci_started_at=%s\n' "${started_at}"
  printf 'home_ci_finished_at=%s\n' "${finished_at}"
} > "${run_root}/status.env"
cp "${run_root}/status.env" "${state_root}/latest-status.env"
rm -rf -- "${worktree}"
rm -f -- "${active_file}"
exit 0

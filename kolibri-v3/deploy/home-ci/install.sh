#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ci_root="${KOLIBRI_HOME_CI_ROOT:-${HOME}/.local/share/kolibri-v3-home-ci}"
state_root="${KOLIBRI_HOME_CI_STATE:-${HOME}/.local/state/kolibri-v3-home-ci}"
libexec_root="${HOME}/.local/libexec"
unit_root="${HOME}/.config/systemd/user"
bare_repo="${ci_root}/repository.git"

mkdir -p "${ci_root}" "${state_root}/runs" "${libexec_root}" "${unit_root}"
chmod 0700 "${ci_root}" "${state_root}" "${state_root}/runs"
if [[ ! -d "${bare_repo}" ]]; then
  git init --bare "${bare_repo}"
fi
git --git-dir="${bare_repo}" config receive.denyNonFastforwards true
git --git-dir="${bare_repo}" config receive.denyDeletes true

install -m 0755 "${script_dir}/runner.sh" \
  "${libexec_root}/kolibri-v3-home-ci-runner"
install -m 0755 "${script_dir}/post-receive" \
  "${bare_repo}/hooks/post-receive"

service_unit="${unit_root}/kolibri-v3-home-ci.service"
path_unit="${unit_root}/kolibri-v3-home-ci.path"
{
  printf '%s\n' \
    '[Unit]' \
    'Description=Kolibri V3 exact-commit Home CI gate' \
    'After=docker.service' \
    '' \
    '[Service]' \
    'Type=oneshot' \
    "ExecStart=${libexec_root}/kolibri-v3-home-ci-runner" \
    'Nice=10' \
    'IOSchedulingClass=best-effort' \
    'IOSchedulingPriority=7' \
    'TimeoutStartSec=2h' \
    'NoNewPrivileges=true' \
    'PrivateTmp=true'
} > "${service_unit}.new"
mv -f "${service_unit}.new" "${service_unit}"
{
  printf '%s\n' \
    '[Unit]' \
    'Description=Watch the Kolibri V3 Home CI exact-commit queue' \
    '' \
    '[Path]' \
    "PathChanged=${state_root}/queue" \
    'Unit=kolibri-v3-home-ci.service' \
    '' \
    '[Install]' \
    'WantedBy=default.target'
} > "${path_unit}.new"
mv -f "${path_unit}.new" "${path_unit}"

systemctl --user daemon-reload
systemctl --user enable --now kolibri-v3-home-ci.path
printf 'home_ci_install=ok\n'
printf 'home_ci_repository=%s\n' "${bare_repo}"
printf 'home_ci_state=%s\n' "${state_root}"


#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="/workspace"
project_root="${repo_root}/kolibri-v3"
evidence_root="/evidence"
expected_commit="${KOLIBRI_HOME_CI_COMMIT:-}"
phase="bootstrap"

fail() {
  printf 'home_ci_error=%s phase=%s\n' "$1" "${phase}" >&2
  exit 2
}

trap 'printf "home_ci_error=command_failed phase=%s line=%s\n" \
  "${phase}" "${LINENO}" >&2' ERR

[[ "${expected_commit}" =~ ^[0-9a-f]{40}$ ]] ||
  fail "commit_invalid"
[[ -d "${repo_root}/.git" && -d "${project_root}" ]] ||
  fail "workspace_invalid"
[[ -d "${evidence_root}" && -w "${evidence_root}" ]] ||
  fail "evidence_directory_invalid"

cache_root="${repo_root}/.home-ci"
python_env="${cache_root}/python"
npm_cache="${cache_root}/npm"
export HOME="${cache_root}/home"
export NPM_CONFIG_CACHE="${npm_cache}"
mkdir -p \
  "${HOME}" \
  "${npm_cache}" \
  "${evidence_root}/release"

git config --global --add safe.directory "${repo_root}"
actual_commit="$(git -C "${repo_root}" rev-parse HEAD)"
[[ "${actual_commit}" == "${expected_commit}" ]] ||
  fail "commit_mismatch"
[[ -z "$(git -C "${repo_root}" status --porcelain --untracked-files=all \
  -- kolibri-v3 .github/workflows/kolibri-v3.yml)" ]] ||
  fail "candidate_not_clean"

printf 'home_ci_commit=%s\n' "${actual_commit}"
printf 'home_ci_node=%s\n' "$(node --version)"
printf 'home_ci_npm=%s\n' "$(npm --version)"
printf 'home_ci_python=%s\n' "$(python --version | tr ' ' '-')"

phase="dependencies"
python -m venv "${python_env}"
"${python_env}/bin/python" -m pip install \
  --disable-pip-version-check \
  -r "${project_root}/backend/requirements-dev.txt" \
  "jsonschema[format-nongpl]==4.25.1"

phase="web"
(
  cd "${project_root}"
  npm ci --cache "${npm_cache}/web"
  npm audit --audit-level=high
  npm run typecheck
  npm test
  npm run build
)

phase="backend"
(
  cd "${project_root}"
  PYTHONPATH=backend \
    "${python_env}/bin/python" -m pytest -q backend/tests
)

phase="contracts"
(
  cd "${project_root}"
  "${python_env}/bin/python" server/generate_contract_manifest.py --check
  "${python_env}/bin/python" server/validate_contracts.py
)

phase="mobile"
(
  cd "${project_root}/apps/kolibri-mobile"
  npm ci --cache "${npm_cache}/mobile"
  npm run typecheck
  npm run lint
  npm test
  npx --yes expo-doctor@1.20.1
  npm run export:ios
  npm run export:android
)

phase="workers"
(
  cd "${project_root}"
  "${python_env}/bin/python" -m unittest discover \
    -s deploy/workers/tests \
    -p 'test_*.py'
)

phase="operations"
operation_root="${cache_root}/systemd"
rm -rf -- "${operation_root}"
mkdir -p \
  "${operation_root}/runtime/backend/venv/bin" \
  "${operation_root}/data" \
  "${operation_root}/backups"
ln -s "${python_env}/bin/python" \
  "${operation_root}/runtime/backend/venv/bin/python"
"${python_env}/bin/python" \
  "${project_root}/deploy/portable/install-contract.py" render-operations \
  --output-dir "${operation_root}" \
  --instance kolibri-v3 \
  --current-link "${operation_root}/runtime" \
  --data-root "${operation_root}/data" \
  --backup-root "${operation_root}/backups" \
  --backend-port 8002 \
  --frontend-port 3103 \
  --public-origin https://kolibriai.example \
  --release-id kolibri-v3-0123456789ab-abcdef012345 \
  --release-commit 0123456789abcdef0123456789abcdef01234567 \
  --expected-schema 44 \
  --systemctl "$(command -v systemctl)" \
  --journalctl "$(command -v journalctl)" \
  --database-helper \
    "${project_root}/deploy/portable/database-rehearsal.py"
for role in backend frontend product-run-worker; do
  printf '%s\n' \
    '[Unit]' \
    "Description=Kolibri V3 Home CI dependency stub (${role})" \
    '[Service]' \
    'Type=oneshot' \
    'ExecStart=/usr/bin/true' \
    > "${operation_root}/kolibri-v3-${role}.service"
done
systemd-analyze verify \
  "${operation_root}/kolibri-v3-backend.service" \
  "${operation_root}/kolibri-v3-frontend.service" \
  "${operation_root}/kolibri-v3-product-run-worker.service" \
  "${operation_root}/kolibri-v3-release-monitor.service" \
  "${operation_root}/kolibri-v3-release-monitor.timer" \
  "${operation_root}/kolibri-v3-database-backup.service" \
  "${operation_root}/kolibri-v3-database-backup.timer"

phase="release"
(
  cd "${project_root}"
  PYTHONPATH=backend \
    "${python_env}/bin/python" deploy/portable/release-manifest.py \
      audit-repository --repo "${repo_root}" --commit HEAD
  ./deploy/portable/build-release.sh "${evidence_root}/release" |
    tee "${evidence_root}/release-build.env"
)
release_archive="$(
  awk -F= '$1 == "release_archive" {print $2; exit}' \
    "${evidence_root}/release-build.env"
)"
[[ -n "${release_archive}" && -f "${release_archive}" ]] ||
  fail "release_archive_missing"
"${python_env}/bin/python" \
  "${project_root}/deploy/portable/release-manifest.py" verify \
  --archive "${release_archive}" |
  tee "${evidence_root}/release-verify.env"

phase="production-smoke"
KOLIBRI_SMOKE_MIN_FREE_KIB=10485760 \
  "${project_root}/deploy/portable/smoke-test.sh" "${release_archive}" |
  tee "${evidence_root}/release-smoke.env"

phase="complete"
printf 'home_ci=ok\n'
printf 'home_ci_commit=%s\n' "${actual_commit}"
printf 'home_ci_archive=%s\n' "${release_archive}"

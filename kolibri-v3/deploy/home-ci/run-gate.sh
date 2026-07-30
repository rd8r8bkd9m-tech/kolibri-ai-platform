#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
project_root="$(cd -- "${script_dir}/../.." && pwd -P)"
repo_root="$(git -C "${project_root}" rev-parse --show-toplevel)"
evidence_root="${1:-}"

[[ -n "${evidence_root}" && "${evidence_root}" = /* ]] || {
  printf '%s\n' \
    'usage: run-gate.sh /absolute/private/evidence-directory' >&2
  exit 2
}
[[ -d "${evidence_root}" && ! -L "${evidence_root}" ]] || {
  printf 'home_ci_error=evidence_directory_invalid path=%s\n' \
    "${evidence_root}" >&2
  exit 2
}
[[ -w "${evidence_root}" ]] || {
  printf 'home_ci_error=evidence_directory_not_writable path=%s\n' \
    "${evidence_root}" >&2
  exit 2
}
command -v docker >/dev/null || {
  printf '%s\n' 'home_ci_error=docker_missing' >&2
  exit 2
}

commit="$(git -C "${repo_root}" rev-parse --verify HEAD)"
[[ "${commit}" =~ ^[0-9a-f]{40}$ ]] || {
  printf '%s\n' 'home_ci_error=commit_invalid' >&2
  exit 2
}
[[ -z "$(git -C "${repo_root}" status --porcelain --untracked-files=all \
  -- kolibri-v3 .github/workflows/kolibri-v3.yml)" ]] || {
  printf '%s\n' 'home_ci_error=candidate_not_clean' >&2
  exit 2
}

image_input_digest="$(
  sha256sum \
    "${script_dir}/Dockerfile" \
    "${script_dir}/Dockerfile.rust" \
    "${script_dir}/gate-inside-container.sh" |
    sha256sum |
    awk '{print substr($1, 1, 12)}'
)"
ci_image="kolibri-v3-home-ci:node24-python312-${image_input_digest}"
rust_image="kolibri-v3-home-ci:rust185-${image_input_digest}"
run_suffix="${commit:0:12}-$$"
main_container="kolibri-v3-home-ci-main-${run_suffix}"
rust_container="kolibri-v3-home-ci-rust-${run_suffix}"

cleanup() {
  docker rm -f "${main_container}" "${rust_container}" \
    >/dev/null 2>&1 || true
}
trap cleanup EXIT

printf 'home_ci_build_image=%s\n' "${ci_image}"
docker build \
  --tag "${ci_image}" \
  --file "${script_dir}/Dockerfile" \
  "${script_dir}"
docker image inspect \
  --format 'home_ci_image_id={{.Id}}' "${ci_image}" |
  tee "${evidence_root}/image.env"
printf 'home_ci_build_image=%s\n' "${rust_image}"
docker build \
  --tag "${rust_image}" \
  --file "${script_dir}/Dockerfile.rust" \
  "${script_dir}"
docker image inspect \
  --format 'home_ci_rust_image_id={{.Id}}' "${rust_image}" |
  tee "${evidence_root}/rust-image.env"

uid="$(id -u)"
gid="$(id -g)"

printf 'home_ci_phase=product_gates\n'
docker run --rm \
  --name "${main_container}" \
  --cpus "${KOLIBRI_HOME_CI_CPUS:-6}" \
  --memory "${KOLIBRI_HOME_CI_MEMORY:-9g}" \
  --memory-swap "${KOLIBRI_HOME_CI_MEMORY_SWAP:-13g}" \
  --pids-limit 2048 \
  --user "${uid}:${gid}" \
  --env "KOLIBRI_HOME_CI_COMMIT=${commit}" \
  --volume "${repo_root}:/workspace" \
  --volume "${evidence_root}:/evidence" \
  --workdir /workspace \
  "${ci_image}" \
  /bin/bash /workspace/kolibri-v3/deploy/home-ci/gate-inside-container.sh

printf 'home_ci_phase=rust_estimate_kernel\n'
docker run --rm \
  --name "${rust_container}" \
  --cpus "${KOLIBRI_HOME_CI_CPUS:-6}" \
  --memory "${KOLIBRI_HOME_CI_MEMORY:-9g}" \
  --memory-swap "${KOLIBRI_HOME_CI_MEMORY_SWAP:-13g}" \
  --pids-limit 1024 \
  --env CARGO_HOME=/tmp/cargo \
  --env CARGO_TARGET_DIR=/tmp/target \
  --volume "${repo_root}:/source:ro" \
  --workdir /source/kolibri-v3/packages/estimate-kernel-rs \
  "${rust_image}" \
  /bin/bash -c '
    set -Eeuo pipefail
    printf "home_ci_rust=%s\n" "$(rustc --version)"
    cargo fmt --check
    cargo test --locked
    cargo clippy --locked --all-targets -- -D warnings
  '

printf 'home_ci=ok\n'
printf 'home_ci_commit=%s\n' "${commit}"

#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
project_root="$(cd -- "$script_dir/../.." && pwd -P)"
repo_root="$(git -C "$project_root" rev-parse --show-toplevel)"
if [[ "$project_root" == "$repo_root" ]]; then
  relative_project="."
elif [[ "$project_root" == "$repo_root/"* ]]; then
  relative_project="${project_root#"$repo_root"/}"
else
  echo "release_error=project_outside_repository" >&2
  exit 2
fi
[[ "$(basename -- "$project_root")" == "kolibri-v3" ]] || {
  echo "release_error=canonical_project_name_required" >&2
  exit 2
}

for command_name in git python3; do
  command -v "$command_name" >/dev/null ||
    { echo "release_error=missing_command command=$command_name" >&2; exit 2; }
done

commit="$(git -C "$repo_root" rev-parse --verify HEAD)"
if [[ -n "$(git -C "$repo_root" status --porcelain --untracked-files=all \
  -- "$relative_project")" ]]; then
  echo "release_error=project_has_uncommitted_changes path=$relative_project" >&2
  exit 2
fi

output_dir="${1:-"$project_root/dist"}"
python3 "$script_dir/release-manifest.py" build \
  --repo "$repo_root" \
  --project "$relative_project" \
  --commit "$commit" \
  --output-dir "$output_dir"

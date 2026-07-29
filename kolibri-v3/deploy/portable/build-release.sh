#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
project_root="$(cd -- "$script_dir/../.." && pwd -P)"
repo_root="$(git -C "$project_root" rev-parse --show-toplevel)"
relative_project="$(git -C "$repo_root" ls-files --full-name "$project_root" | head -n 1)"

if [[ -z "$relative_project" ]]; then
  relative_project="${project_root#"$repo_root"/}"
fi

commit="$(git -C "$repo_root" rev-parse HEAD)"
if [[ -n "$(git -C "$repo_root" status --porcelain --untracked-files=all \
  -- "$relative_project")" ]]; then
  echo "release_error=project_has_uncommitted_changes path=$relative_project" >&2
  exit 2
fi

output_dir="${1:-"$project_root/dist"}"
mkdir -p "$output_dir"
output_dir="$(cd "$output_dir" && pwd -P)"
archive="$output_dir/kolibri-v3-${commit:0:12}.tar.gz"

git -C "$repo_root" archive \
  --format=tar.gz \
  --prefix=kolibri-v3/ \
  --output="$archive" \
  "$commit:$relative_project"

if command -v sha256sum >/dev/null; then
  archive_sha256="$(sha256sum "$archive" | awk '{print $1}')"
else
  archive_sha256="$(shasum -a 256 "$archive" | awk '{print $1}')"
fi
printf '%s  %s\n' "$archive_sha256" "$(basename "$archive")" > "$archive.sha256"
cat > "$archive.manifest" <<EOF
format=kolibri-v3-portable-v1
commit=$commit
archive=$(basename "$archive")
sha256=$archive_sha256
EOF

echo "release_archive=$archive"
echo "release_sha256=$archive_sha256"
echo "release_commit=$commit"

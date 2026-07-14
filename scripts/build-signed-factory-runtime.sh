#!/usr/bin/env bash
set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUTPUT_DIR="${ROOT}/dist/factory-runtime"
SIGNING_KEY=""
RELEASE_ID=""

usage() {
  echo "usage: $0 --signing-key PRIVATE_PEM [--output-dir DIR] [--release-id ID]" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --signing-key) SIGNING_KEY=$2; shift 2 ;;
    --output-dir) OUTPUT_DIR=$2; shift 2 ;;
    --release-id) RELEASE_ID=$2; shift 2 ;;
    *) usage ;;
  esac
done

[[ -n "$SIGNING_KEY" && -f "$SIGNING_KEY" ]] || usage
command -v git >/dev/null
command -v gzip >/dev/null
command -v openssl >/dev/null
command -v python3 >/dev/null
if ! openssl pkey -in "$SIGNING_KEY" -text -noout 2>/dev/null | grep -qi "ED25519"; then
  echo "signing_key_must_be_ed25519" >&2
  exit 1
fi

SOURCE_COMMIT=$(git -C "$ROOT" rev-parse --verify HEAD)
if [[ -z "$RELEASE_ID" ]]; then
  RELEASE_ID="factory-p7-${SOURCE_COMMIT:0:12}"
fi
if [[ ! "$RELEASE_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "invalid_release_id:$RELEASE_ID" >&2
  exit 1
fi

FILES=(
  ops/agent_host.py
  ops/factory_control.py
  ops/fleet_classification.py
  ops/systemd/kolibri-agent-host.service
  ops/systemd/kolibri-factory-control.service
  scripts/preflight-factory-control-runtime.sh
)
for file in "${FILES[@]}"; do
  git -C "$ROOT" cat-file -e "${SOURCE_COMMIT}:${file}" || {
    echo "runtime_file_not_tracked:${file}" >&2
    exit 1
  }
done

mkdir -p "$OUTPUT_DIR"
umask 077
TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/kolibri-runtime-build.XXXXXX")
trap 'rm -rf "$TMP_DIR"' EXIT

BUNDLE_NAME="${RELEASE_ID}.tar.gz"
BUNDLE_PATH="${OUTPUT_DIR}/${BUNDLE_NAME}"
MANIFEST_PATH="${OUTPUT_DIR}/${RELEASE_ID}.manifest.json"
SIGNATURE_PATH="${OUTPUT_DIR}/${RELEASE_ID}.manifest.sig"
PUBLIC_KEY_PATH="${OUTPUT_DIR}/${RELEASE_ID}.signing-public.pem"
FILE_INDEX="${TMP_DIR}/files.tsv"

openssl pkey -in "$SIGNING_KEY" -pubout -out "$PUBLIC_KEY_PATH"
PUBLIC_KEY_FINGERPRINT=$(openssl pkey -pubin -in "$PUBLIC_KEY_PATH" -outform DER | openssl dgst -sha256 -r | awk '{print $1}')

git -C "$ROOT" archive --format=tar "$SOURCE_COMMIT" "${FILES[@]}" | gzip -n >"$BUNDLE_PATH"
: >"$FILE_INDEX"
for file in "${FILES[@]}"; do
  git -C "$ROOT" show "${SOURCE_COMMIT}:${file}" >"${TMP_DIR}/payload"
  FILE_SHA=$(openssl dgst -sha256 -r "${TMP_DIR}/payload" | awk '{print $1}')
  FILE_BYTES=$(wc -c <"${TMP_DIR}/payload" | tr -d ' ')
  printf '%s\t%s\t%s\n' "$file" "$FILE_SHA" "$FILE_BYTES" >>"$FILE_INDEX"
done

BUNDLE_SHA=$(openssl dgst -sha256 -r "$BUNDLE_PATH" | awk '{print $1}')
BUNDLE_BYTES=$(wc -c <"$BUNDLE_PATH" | tr -d ' ')
GENERATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)

RELEASE_ID="$RELEASE_ID" SOURCE_COMMIT="$SOURCE_COMMIT" BUNDLE_NAME="$BUNDLE_NAME" \
BUNDLE_SHA="$BUNDLE_SHA" BUNDLE_BYTES="$BUNDLE_BYTES" GENERATED_AT="$GENERATED_AT" \
PUBLIC_KEY_FINGERPRINT="$PUBLIC_KEY_FINGERPRINT" FILE_INDEX="$FILE_INDEX" MANIFEST_PATH="$MANIFEST_PATH" python3 - <<'PY'
import json
import os
from pathlib import Path

files = []
for line in Path(os.environ["FILE_INDEX"]).read_text(encoding="utf-8").splitlines():
    path, sha256, size = line.split("\t")
    files.append({"path": path, "sha256": sha256, "bytes": int(size)})

manifest = {
    "schema": "kolibri.factory.runtime-manifest/v1",
    "release_id": os.environ["RELEASE_ID"],
    "source_commit": os.environ["SOURCE_COMMIT"],
    "lease_contract_version": "2026-07-14.lease-v1",
    "generated_at": os.environ["GENERATED_AT"],
    "authority": "home",
    "activation": "owner_approval_required",
    "signing_key_fingerprint_sha256": os.environ["PUBLIC_KEY_FINGERPRINT"],
    "bundle": {
        "name": os.environ["BUNDLE_NAME"],
        "sha256": os.environ["BUNDLE_SHA"],
        "bytes": int(os.environ["BUNDLE_BYTES"]),
    },
    "files": files,
}
Path(os.environ["MANIFEST_PATH"]).write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

openssl pkeyutl -sign -rawin -inkey "$SIGNING_KEY" -in "$MANIFEST_PATH" -out "$SIGNATURE_PATH"
"${ROOT}/scripts/verify-signed-factory-runtime.sh" \
  --manifest "$MANIFEST_PATH" \
  --signature "$SIGNATURE_PATH" \
  --public-key "$PUBLIC_KEY_PATH" \
  --bundle "$BUNDLE_PATH"

printf '%s\n' "$MANIFEST_PATH"

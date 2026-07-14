#!/usr/bin/env bash
set -euo pipefail

MANIFEST=""
SIGNATURE=""
PUBLIC_KEY=""
BUNDLE=""

usage() {
  echo "usage: $0 --manifest FILE --signature FILE --public-key PINNED_PEM --bundle FILE" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --manifest) MANIFEST=$2; shift 2 ;;
    --signature) SIGNATURE=$2; shift 2 ;;
    --public-key) PUBLIC_KEY=$2; shift 2 ;;
    --bundle) BUNDLE=$2; shift 2 ;;
    *) usage ;;
  esac
done

for file in "$MANIFEST" "$SIGNATURE" "$PUBLIC_KEY" "$BUNDLE"; do
  [[ -n "$file" && -f "$file" ]] || usage
done
command -v openssl >/dev/null
command -v python3 >/dev/null

openssl pkeyutl -verify -pubin -rawin -inkey "$PUBLIC_KEY" \
  -in "$MANIFEST" -sigfile "$SIGNATURE" >/dev/null

MANIFEST="$MANIFEST" BUNDLE="$BUNDLE" python3 - <<'PY'
import hashlib
import json
import os
import tarfile
from pathlib import Path, PurePosixPath

manifest = json.loads(Path(os.environ["MANIFEST"]).read_text(encoding="utf-8"))
bundle_path = Path(os.environ["BUNDLE"])
if manifest.get("schema") != "kolibri.factory.runtime-manifest/v1":
    raise SystemExit("runtime_manifest_schema_mismatch")
if manifest.get("authority") != "home":
    raise SystemExit("runtime_manifest_authority_mismatch")
if manifest.get("activation") != "owner_approval_required":
    raise SystemExit("runtime_manifest_activation_policy_mismatch")

bundle = manifest.get("bundle") or {}
payload = bundle_path.read_bytes()
if hashlib.sha256(payload).hexdigest() != bundle.get("sha256"):
    raise SystemExit("runtime_bundle_sha256_mismatch")
if len(payload) != bundle.get("bytes"):
    raise SystemExit("runtime_bundle_size_mismatch")

expected = {item["path"]: item for item in manifest.get("files") or []}
observed = {}
with tarfile.open(bundle_path, "r:gz") as archive:
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise SystemExit(f"runtime_bundle_unsafe_path:{member.name}")
        if not member.isfile():
            continue
        stream = archive.extractfile(member)
        if stream is None:
            raise SystemExit(f"runtime_bundle_unreadable:{member.name}")
        data = stream.read()
        observed[member.name] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }

if set(observed) != set(expected):
    raise SystemExit("runtime_bundle_file_set_mismatch")
for path, item in expected.items():
    if observed[path] != {"sha256": item["sha256"], "bytes": item["bytes"]}:
        raise SystemExit(f"runtime_bundle_file_evidence_mismatch:{path}")

print(json.dumps({
    "status": "verified",
    "release_id": manifest["release_id"],
    "source_commit": manifest["source_commit"],
    "bundle_sha256": bundle["sha256"],
}, sort_keys=True))
PY

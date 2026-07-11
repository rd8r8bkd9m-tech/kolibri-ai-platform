# First Home rollback snapshot contract

Status: protected release-building procedure, 2026-07-11. This procedure does
not authorize a Home mutation, signing operation, staging operation or release
apply.

Use this procedure only for the first migration where the current signed
product release is immutable but the effective Agent Host and Control Plane
runtime is still split across bootstrap paths. Once `current` is a complete
unified signed release, rollback is a direct signed snapshot of that release
and this compatibility procedure is no longer valid.

## Why the historical tar recipe is forbidden

The former recipe selected broad directories and silently excluded
`__pycache__`, logs and secret-like names. That cannot prove which files were
present, which bytes came from the signed release, or whether an unbound file
was omitted. It also created `RELEASE_ID` from the source release directory and
then built a differently named rollback release. Home policy compares the
payload marker to the new manifest `release_id`, so that bundle is
deterministically rejected as `release_id_marker_invalid`.

The identities have different meanings and must never be reused:

- `SOURCE_RELEASE_ID` is read from the verified current signed manifest and is
  recorded only in `ROLLBACK_PROVENANCE.json`;
- `ROLLBACK_ID` is the new signed rollback release identity and is the exact
  content of `RELEASE_ID`, the builder `--release-id`, the artifact name and the
  approval rollback identity.

## Required inputs

Run the helper where it has a direct read-only view of the exact Home paths (or
an owner-approved root-only scratch capture that preserves the complete tree
inventory). Acquiring that view is a protected operator transport step; do not
replace effective bytes with a newer checkout.

`CURRENT_CAPTURE` must expose the original signed current release metadata,
every manifest-bound file and every other directory entry. File modes must be
preserved. Do not use exclude globs or a manifest-only copy: either would hide
pollution from the inventory gate. The snapshot helper verifies the original
`sshsig`, canonical manifest, every manifest file hash/size/mode and inventories
every unbound entry without reading the unbound file contents.

Each split-runtime mapping must point to the exact file used by the active
service at capture time. Resolve that fact from the effective systemd
`ExecStart` and process/module evidence before capture. The required mapping
destinations are fixed:

```text
ops/agent_host.py
ops/control_plane_endpoint.py
ops/factory_control.py
ops/fleet_membership.py
ops/immutable_release_preflight.py
ops/release_authority.py
ops/release_helper.py
ops/release_installer.py
ops/runner_access.py
ops/telegram_superfactory.py
```

`ops/immutable_release_preflight.py` may be mapped only after the protected
authority bridge has installed that exact read-only gate and the effective
release policy invokes it. If it is absent or differs from the policy's active
executable, rollback capture remains blocked; it is not silently substituted
from the candidate checkout.

If `ops/mimo/kolibri-response-only.md` was effective, pass its exact active
path with `--mimo-effective-source`. If it was absent, pass a committed source
file with `--mimo-sentinel-source`, its source commit and expected SHA-256. The
provenance then states explicitly that this required compatibility sentinel was
not active; its presence must not be presented as known-good runtime evidence.

## Read-only plan, explicit pollution acknowledgement, capture

Choose the new rollback identity before creating any marker:

```bash
set -euo pipefail

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
ROLLBACK_ID="rollback-${SOURCE_RELEASE_ID}-${STAMP}"
ROLLBACK_PARENT=$(mktemp -d "${TMPDIR:-/tmp}/kolibri-rollback.XXXXXXXX")
chmod 0700 "$ROLLBACK_PARENT"
ROLLBACK_ROOT="$ROLLBACK_PARENT/source"
ROLLBACK_PLAN="$ROLLBACK_PARENT/plan.json"

COMMON_SNAPSHOT_ARGS=(
  --current-root "$CURRENT_CAPTURE"
  --snapshot-root "$ROLLBACK_ROOT"
  --rollback-release-id "$ROLLBACK_ID"
  --allowed-signers "$ALLOWED_SIGNERS_SNAPSHOT"
  --signer-identity "$SIGNER_ID"
  --runtime-map "ops/agent_host.py=$ACTIVE_AGENT_HOST"
  --runtime-map "ops/control_plane_endpoint.py=$ACTIVE_CONTROL_PLANE_ENDPOINT"
  --runtime-map "ops/factory_control.py=$ACTIVE_FACTORY_CONTROL"
  --runtime-map "ops/fleet_membership.py=$ACTIVE_FLEET_MEMBERSHIP"
  --runtime-map "ops/immutable_release_preflight.py=$ACTIVE_IMMUTABLE_RELEASE_PREFLIGHT"
  --runtime-map "ops/release_authority.py=$ACTIVE_RELEASE_AUTHORITY"
  --runtime-map "ops/release_helper.py=$ACTIVE_RELEASE_HELPER"
  --runtime-map "ops/release_installer.py=$ACTIVE_RELEASE_INSTALLER"
  --runtime-map "ops/runner_access.py=$ACTIVE_RUNNER_ACCESS"
  --runtime-map "ops/telegram_superfactory.py=$ACTIVE_TELEGRAM_SUPERFACTORY"
  --mimo-sentinel-source "$SOURCE_ROOT/ops/mimo/kolibri-response-only.md"
  --mimo-sentinel-commit "$SOURCE_COMMIT"
  --mimo-sentinel-sha256 "$MIMO_SENTINEL_SHA256"
)

python3 ops/release_rollback_snapshot.py plan \
  "${COMMON_SNAPSHOT_ARGS[@]}" >"$ROLLBACK_PLAN" || test $? -eq 2
```

The plan exits `2` with `status=blocked` when any unbound entry exists. This is
expected for a polluted source, but it is not an automatic waiver. Review the
metadata-only `unbound_entries.records`; the helper never reads their contents.
If and only if every listed entry is confirmed non-runtime pollution, bind the
exact inventory digest into the capture:

```bash
UNBOUND_DIGEST=$(python3 - "$ROLLBACK_PLAN" <<'PY'
import json, pathlib, sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(value["unbound_entries"]["digest"])
PY
)

python3 ops/release_rollback_snapshot.py capture \
  "${COMMON_SNAPSHOT_ARGS[@]}" \
  --acknowledge-unbound-digest "$UNBOUND_DIGEST"
```

When the plan has zero unbound entries, omit
`--acknowledge-unbound-digest`. A changed source inventory, changed bound file,
symlink, special file, missing map, wrong sentinel digest or output collision
fails closed and removes the partial local snapshot.

## Provenance commit and signed bundle

The helper writes only manifest-bound product files, explicitly mapped runtime
files, the new marker and canonical provenance. Commit that exact tree in an
isolated private repository, then verify it again:

```bash
git -C "$ROLLBACK_ROOT" init -q
git -C "$ROLLBACK_ROOT" add \
  backend frontend ops RELEASE_ID ROLLBACK_PROVENANCE.json
git -C "$ROLLBACK_ROOT" \
  -c user.name='Kolibri Release Snapshot' \
  -c user.email='release-snapshot@kolibriai.local' \
  commit -q -m "snapshot: $ROLLBACK_ID"
ROLLBACK_SOURCE_COMMIT=$(git -C "$ROLLBACK_ROOT" rev-parse HEAD)

python3 ops/release_rollback_snapshot.py verify \
  --snapshot-root "$ROLLBACK_ROOT"

ROLLBACK_BUNDLE="$RELEASE_WORK/bundles/$ROLLBACK_ID.tar.gz"
python3 ops/release_bundle_builder.py \
  --root "$ROLLBACK_ROOT" \
  --release-id "$ROLLBACK_ID" \
  --source-commit "$ROLLBACK_SOURCE_COMMIT" \
  --artifact-uri "artifact://bundles/$ROLLBACK_ID.tar.gz" \
  --output "$ROLLBACK_BUNDLE" \
  --runtime-path RELEASE_ID \
  --runtime-path ROLLBACK_PROVENANCE.json \
  --runtime-path ops/agent_host.py \
  --runtime-path ops/control_plane_endpoint.py \
  --runtime-path ops/factory_control.py \
  --runtime-path ops/fleet_membership.py \
  --runtime-path ops/immutable_release_preflight.py \
  --runtime-path ops/mimo/kolibri-response-only.md \
  --runtime-path ops/release_authority.py \
  --runtime-path ops/release_helper.py \
  --runtime-path ops/release_installer.py \
  --runtime-path ops/runner_access.py \
  --runtime-path ops/telegram_superfactory.py \
  --build --sign \
  --signer-identity "$SIGNER_ID" \
  --signing-key "$OWNER_KEY"
```

Do not continue unless `self_verified=true`, the built manifest has
`release_id=$ROLLBACK_ID`, its `RELEASE_ID` record hashes the exact bytes
`$ROLLBACK_ID\n`, the full unified path profile is present, and the provenance
file is part of the signed manifest. Staging and approval remain governed by
`HOME_CONTROL_PLANE_SIGNED_RELEASE.md`.

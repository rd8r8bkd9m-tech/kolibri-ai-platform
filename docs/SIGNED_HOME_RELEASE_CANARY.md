# Signed Home-only release canary (legacy backend procedure)

> The active Home policy now requires a unified backend/frontend/Control Plane
> bundle. Do not execute this historical backend-only procedure as written.
> Use `docs/HOME_CONTROL_PLANE_SIGNED_RELEASE.md`; the extraction and approval
> sections below remain reference material.

Status: executable runbook. No production release was applied while this
runbook was implemented.

This path changes only the canonical Home backend release. Bundle publication
is an owner/bootstrap transport into the root-only artifact store. Activation
and rollback are exclusively fenced Control Plane API tasks; SSH is never used
as worker execution.

## 1. Preconditions

Run from a clean, committed canonical worktree. The frontend production build
must have passed, Home must be the only Control Plane, and its active node card
must be fresh with `release_apply_v1`.

```bash
set -euo pipefail

export WORKTREE=${WORKTREE:?canonical worktree required}
export MESH_MANIFEST=${MESH_MANIFEST:-$HOME/.kolibri-mesh/peers.json}
export OWNER_KEY=${KOLIBRI_RELEASE_SIGNING_KEY:?private key path required}
export OWNER_PUBLIC_KEY=${KOLIBRI_RELEASE_SIGNING_PUBLIC_KEY:?public key path required}
export SIGNER_ID=${KOLIBRI_RELEASE_SIGNER_ID:?installed signer identity required}

cd "$WORKTREE"
test -z "$(git status --porcelain --untracked-files=no)"
test -z "$(git ls-files --others --exclude-standard -- \
  backend frontend/src frontend/public frontend/package.json frontend/vite.config.js)"
SOURCE_COMMIT=$(git rev-parse HEAD)
test "$(git cat-file -t "$SOURCE_COMMIT")" = commit

export RELEASE_WORK=${KOLIBRI_RELEASE_WORK:-$HOME/.kolibri-release}
install -d -m 0700 "$RELEASE_WORK" "$RELEASE_WORK/bundles" "$RELEASE_WORK/control"

npm --prefix frontend ci
npm --prefix frontend run test
npm --prefix frontend run lint
npm --prefix frontend run build

HOME_URL=$(PYTHONPATH=. python3 ops/control_plane_endpoint.py \
  --print-url --manifest "$MESH_MANIFEST")
curl --fail --silent --show-error --max-time 5 "$HOME_URL/v1/health" >/dev/null
```

## 2. Capture and sign the rollback bundle first

The rollback payload is a new signed immutable bundle made from the exact
current Home release, not a mutable repository checkout. Only code and built
frontend paths are transferred; common credential filenames and key suffixes
are excluded before bytes leave Home. The copied payload is scanned again,
committed in an isolated local snapshot repository, and that real snapshot
commit becomes its provenance.

```bash
HOME_HOST=$(python3 -c \
  'import sys,urllib.parse; print(urllib.parse.urlsplit(sys.argv[1]).hostname or "")' \
  "$HOME_URL")
REMOTE="root@$HOME_HOST"
CURRENT_REAL=$(ssh -o BatchMode=yes -o ConnectTimeout=8 "$REMOTE" \
  /usr/bin/readlink -f /opt/kolibri-ai/current)
case "$CURRENT_REAL" in
  /opt/kolibri-ai/releases/*) ;;
  *) exit 2 ;;
esac
CURRENT_RELEASE_ID=$(basename "$CURRENT_REAL")
case "$CURRENT_RELEASE_ID" in
  ""|*[!A-Za-z0-9._-]*) exit 2 ;;
esac

ROLLBACK_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/kolibri-rollback.XXXXXXXX")
chmod 0700 "$ROLLBACK_ROOT"
ssh -o BatchMode=yes -o ConnectTimeout=8 "$REMOTE" \
  /usr/bin/tar -C "$CURRENT_REAL" \
  --exclude='*/__pycache__' --exclude='backend/tests' \
  --exclude='*/.env' --exclude='*/.env.*' \
  --exclude='*/auth.json' --exclude='*/cookies.json' \
  --exclude='*/credentials.json' --exclude='*/secret.json' \
  --exclude='*/secrets.json' --exclude='*/telegram.env' \
  --exclude='*/tokens.json' --exclude='*.key' --exclude='*.pem' \
  --exclude='*.p12' --exclude='*.pfx' \
  -cf - backend frontend/dist ops/control_plane_endpoint.py \
  | tar -C "$ROLLBACK_ROOT" -xf -

ROLLBACK_ROOT="$ROLLBACK_ROOT" python3 - <<'PY'
import os, re
from pathlib import Path
root = Path(os.environ["ROLLBACK_ROOT"])
patterns = (
    re.compile(rb"-----BEGIN (?:OPENSSH|RSA|EC|DSA) PRIVATE KEY-----"),
    re.compile(rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(rb"\b[0-9]{8,12}:[A-Za-z0-9_-]{30,}\b"),
)
files = [path for path in root.rglob("*") if path.is_file()]
if not files or any(path.is_symlink() for path in root.rglob("*")):
    raise SystemExit("rollback_snapshot_invalid")
if any(pattern.search(path.read_bytes()) for path in files for pattern in patterns):
    raise SystemExit("rollback_snapshot_secret_risk")
PY

# Historical releases may predate the RELEASE_ID payload marker. Derive it
# from the already validated immutable release-directory name and create it
# only in this private local snapshot. Never write into CURRENT_REAL.
python3 ops/release_snapshot_marker.py \
  --root "$ROLLBACK_ROOT" --release-id "$CURRENT_RELEASE_ID"

git -C "$ROLLBACK_ROOT" init -q
git -C "$ROLLBACK_ROOT" add backend frontend ops RELEASE_ID
git -C "$ROLLBACK_ROOT" \
  -c user.name='Kolibri Release Snapshot' \
  -c user.email='release-snapshot@kolibriai.local' \
  commit -q -m "snapshot: $CURRENT_RELEASE_ID rollback payload"
ROLLBACK_SOURCE_COMMIT=$(git -C "$ROLLBACK_ROOT" rev-parse HEAD)

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
ROLLBACK_ID="rollback-${CURRENT_RELEASE_ID}-${STAMP}"
ROLLBACK_BUNDLE="$RELEASE_WORK/bundles/$ROLLBACK_ID.tar.gz"
python3 ops/release_bundle_builder.py \
  --root "$ROLLBACK_ROOT" \
  --release-id "$ROLLBACK_ID" \
  --source-commit "$ROLLBACK_SOURCE_COMMIT" \
  --artifact-uri "artifact://bundles/$ROLLBACK_ID.tar.gz" \
  --output "$ROLLBACK_BUNDLE" \
  --runtime-path ops/control_plane_endpoint.py \
  --runtime-path RELEASE_ID \
  --build --sign \
  --signer-identity "$SIGNER_ID" \
  --signing-key "$OWNER_KEY"
```

Do not proceed unless the builder reports `self_verified=true`.

## 3. Build the committed backend and frontend bundle

Build from an isolated archive of the exact committed source. This keeps the
generated frontend and release marker out of the canonical worktree while
binding every source byte to `SOURCE_COMMIT`.

```bash
RELEASE_ID="kolibri-${STAMP}-${SOURCE_COMMIT:0:12}"
RELEASE_BUNDLE="$RELEASE_WORK/bundles/$RELEASE_ID.tar.gz"
SOURCE_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/kolibri-source.XXXXXXXX")
chmod 0700 "$SOURCE_ROOT"
git archive --format=tar "$SOURCE_COMMIT" | tar -C "$SOURCE_ROOT" -xf -

npm --prefix "$SOURCE_ROOT/frontend" ci
npm --prefix "$SOURCE_ROOT/frontend" run build
python3 ops/release_snapshot_marker.py \
  --root "$SOURCE_ROOT" --release-id "$RELEASE_ID"

python3 ops/release_bundle_builder.py \
  --root "$SOURCE_ROOT" \
  --release-id "$RELEASE_ID" \
  --source-commit "$SOURCE_COMMIT" \
  --artifact-uri "artifact://bundles/$RELEASE_ID.tar.gz" \
  --output "$RELEASE_BUNDLE" \
  --runtime-path ops/control_plane_endpoint.py \
  --runtime-path RELEASE_ID \
  --build --sign \
  --signer-identity "$SIGNER_ID" \
  --signing-key "$OWNER_KEY"
```

Export only the fixed manifest and detached signature members for the
controller. The function refuses overwrite and unknown member shapes.

```bash
extract_release_control() {
  python3 - "$1" "$2" <<'PY'
import os, pathlib, stat, sys, tarfile
bundle = pathlib.Path(sys.argv[1])
target = pathlib.Path(sys.argv[2])
target.mkdir(mode=0o700, parents=True, exist_ok=False)
with tarfile.open(bundle, "r:gz") as archive:
    members = {item.name: item for item in archive.getmembers()}
    wanted = {
        ".kolibri-release/manifest.json": "manifest.json",
        ".kolibri-release/manifest.sig": "manifest.sig",
    }
    for source, name in wanted.items():
        member = members.get(source)
        if member is None or not member.isfile() or member.size <= 0:
            raise SystemExit("release_control_member_invalid")
        stream = archive.extractfile(member)
        if stream is None:
            raise SystemExit("release_control_member_invalid")
        payload = stream.read()
        descriptor = os.open(target / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
PY
}

CONTROL_ROOT="$RELEASE_WORK/control/$RELEASE_ID"
extract_release_control "$RELEASE_BUNDLE" "$CONTROL_ROOT/current"
extract_release_control "$ROLLBACK_BUNDLE" "$CONTROL_ROOT/rollback"
```

Create a private local allowed-signers snapshot from public material only:

```bash
python3 - "$OWNER_PUBLIC_KEY" "$CONTROL_ROOT/allowed_signers" "$SIGNER_ID" <<'PY'
import os, pathlib, re, sys
source, target, identity = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
parts = source.read_text(encoding="utf-8").strip().split()
if len(parts) < 2 or not re.fullmatch(r"[A-Za-z0-9@._:+-]+", identity):
    raise SystemExit("allowed_signers_input_invalid")
payload = f"{identity} {parts[0]} {parts[1]}\n".encode()
descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
with os.fdopen(descriptor, "wb") as output:
    output.write(payload)
PY
```

## 4. Stage both bundles without activation

Run each command first without `--apply`; only the explicit second pass
publishes an immutable root-owned artifact. Existing different bytes are a
hard collision.

```bash
scripts/stage-home-release-bundle.sh \
  --manifest "$MESH_MANIFEST" --bundle "$ROLLBACK_BUNDLE"
scripts/stage-home-release-bundle.sh \
  --manifest "$MESH_MANIFEST" --bundle "$RELEASE_BUNDLE"

scripts/stage-home-release-bundle.sh \
  --manifest "$MESH_MANIFEST" --bundle "$ROLLBACK_BUNDLE" --apply
scripts/stage-home-release-bundle.sh \
  --manifest "$MESH_MANIFEST" --bundle "$RELEASE_BUNDLE" --apply
```

These are owner/bootstrap artifact writes only. They do not restart a service,
move `current`, or execute a worker task.

## 5. Bind, sign, and submit the short-lived owner approval

`--home-only --expected-nodes 21` checks the complete canonical membership but
produces exactly one rollout wave containing Home.

```bash
ROLLOUT_PLAN="$CONTROL_ROOT/home-rollout.json"
python3 ops/release_controller.py plan \
  --manifest "$CONTROL_ROOT/current/manifest.json" \
  --home-only --expected-nodes 21 --control-url "$HOME_URL" \
  >"$ROLLOUT_PLAN"

APPROVAL_ID="approval-$RELEASE_ID"
APPROVAL_NONCE=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
APPROVAL_EXPIRES=$(python3 -c \
  'from datetime import datetime,timedelta,timezone; print((datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat())')
APPROVAL_FILE="$CONTROL_ROOT/owner-approval.json"

APPROVAL_BINDING=(
  --manifest "$CONTROL_ROOT/current/manifest.json"
  --signature "$CONTROL_ROOT/current/manifest.sig"
  --rollback-manifest "$CONTROL_ROOT/rollback/manifest.json"
  --rollback-signature "$CONTROL_ROOT/rollback/manifest.sig"
  --allowed-signers "$CONTROL_ROOT/allowed_signers"
  --release-signer-identity "$SIGNER_ID"
  --rollout-plan "$ROLLOUT_PLAN"
  --approval-id "$APPROVAL_ID"
  --expires-at "$APPROVAL_EXPIRES"
  --nonce "$APPROVAL_NONCE"
  --owner-signer-identity "$SIGNER_ID"
)

python3 ops/release_approval.py plan "${APPROVAL_BINDING[@]}"
python3 ops/release_approval.py sign "${APPROVAL_BINDING[@]}" \
  --owner-signing-key "$OWNER_KEY" --output "$APPROVAL_FILE"
python3 ops/release_approval.py submit \
  --approval-file "$APPROVAL_FILE" \
  --allowed-signers "$CONTROL_ROOT/allowed_signers" \
  --control-url "$HOME_URL"
```

The signing command never reads the private key bytes in Python and never
prints the key path. `submit` locally reverifies the owner signature before it
contacts Home.

## 6. API-only Home canary and rollback gate

```bash
python3 ops/release_controller.py apply \
  --manifest "$CONTROL_ROOT/current/manifest.json" \
  --signature "$CONTROL_ROOT/current/manifest.sig" \
  --rollback-manifest "$CONTROL_ROOT/rollback/manifest.json" \
  --rollback-signature "$CONTROL_ROOT/rollback/manifest.sig" \
  --allowed-signers "$CONTROL_ROOT/allowed_signers" \
  --signer-identity "$SIGNER_ID" \
  --approval-id "$APPROVAL_ID" \
  --home-only --expected-nodes 21 --control-url "$HOME_URL"
```

The controller submits `release_bundle_apply` through `/v1/tasks`, waits for a
fenced terminal result, and then requires Home release health bound to the
manifest digest. On the first failure it cancels and fences unfinished apply
tasks, submits the approved `release_bundle_rollback` for each attempted node,
and requires rollback health. A nonzero controller result is never release
success.

## 7. Evidence smoke

After `status=completed`, verify the Control Plane record and public surface:

```bash
curl --fail --silent --show-error \
  "$HOME_URL/v1/releases/$RELEASE_ID/nodes/home/health" \
  | python3 -c \
    'import json,sys; v=json.load(sys.stdin); assert v["status"]=="healthy" and v["manifest_digest"].startswith("sha256:")'

curl --fail --silent --show-error https://kolibriai.ru/api/health >/dev/null
curl --fail --silent --show-error https://kolibriai.ru/v1/models \
  | python3 -c \
    'import json,sys; v=json.load(sys.stdin); rows=v.get("data",v).get("data",[]) if isinstance(v.get("data"),dict) else v.get("data",[]); assert [r.get("id") for r in rows]==["kolibri"]'

COOKIE_JAR=$(mktemp "${TMPDIR:-/tmp}/kolibri-session.XXXXXXXX")
chmod 0600 "$COOKIE_JAR"
curl --fail --silent --show-error \
  -H 'Origin: https://kolibriai.ru' \
  -c "$COOKIE_JAR" -X POST https://kolibriai.ru/v1/public/session >/dev/null
curl --fail --silent --show-error \
  -H 'Origin: https://kolibriai.ru' \
  -H "Idempotency-Key: smoke-$RELEASE_ID" \
  -H 'Content-Type: application/json' \
  -b "$COOKIE_JAR" \
  --data '{"model":"kolibri","input":"Привет. Ответь одним словом: Kolibri"}' \
  https://kolibriai.ru/v1/responses \
  | python3 -c \
    'import json,sys; v=json.load(sys.stdin); assert v["status"]=="completed" and v["model"]=="kolibri" and str(v.get("output_text") or "").strip()'

curl --fail --silent --show-error https://kolibriai.ru/sw.js \
  | python3 -c \
    'import sys; s=sys.stdin.read(); assert "registration.unregister" in s and ".put(" not in s and "caches.open" not in s'
```

Finally use a real browser session: reload the Shell, send a second message in
the same conversation, confirm exactly one assistant response, verify stale
public-session recovery occurs without a page reload, and require a clean
console for `public_session_required_or_expired`, `Method Not Allowed`, 404/422
chat routes, and unsupported `chrome-extension` cache writes. Screenshots,
network evidence, response ID, task ID, release health and manifest digest are
the acceptance artifacts.

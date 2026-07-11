# Home owner API token: one-time audited provisioning

Status: operator runbook. No credential was created and no Home service was
restarted while this runbook was written.

The protected Project, Knowledge and Telegram paths share one root-managed
owner bearer token. The token value is never placed in a systemd environment,
release bundle, Git tree, task result, log, shell output or Telegram message.
The canonical backend and Telegram units receive only this path:

```text
/etc/kolibri/owner-api-token
```

The required metadata is one non-symlink regular file, `root:kolibri-agent`,
mode `0640`, with a non-empty bounded value. Release preflight and the backend
drop-in bootstrap fail closed until that metadata is present.

## 1. Read-only target and absence proof

Resolve Home from dynamic membership; do not embed its current IP:

```bash
set -euo pipefail
MESH_MANIFEST=${MESH_MANIFEST:-$HOME/.kolibri-mesh/peers.json}
HOME_URL=$(PYTHONPATH=. python3 ops/control_plane_endpoint.py \
  --print-url --manifest "$MESH_MANIFEST")
HOME_HOST=$(python3 -c \
  'import sys,urllib.parse; print(urllib.parse.urlsplit(sys.argv[1]).hostname or "")' \
  "$HOME_URL")
REMOTE="root@$HOME_HOST"

ssh -o BatchMode=yes -o ConnectTimeout=8 "$REMOTE" /usr/bin/python3 - <<'PY'
import json, os, pathlib, stat
p = pathlib.Path("/etc/kolibri/owner-api-token")
if not os.path.lexists(p):
    print(json.dumps({"status": "absent", "secret_read": False}, sort_keys=True))
else:
    value = p.lstat()
    print(json.dumps({
        "status": "present",
        "regular": stat.S_ISREG(value.st_mode),
        "symlink": stat.S_ISLNK(value.st_mode),
        "mode": f"{stat.S_IMODE(value.st_mode):04o}",
        "uid": value.st_uid,
        "gid": value.st_gid,
        "secret_read": False,
    }, sort_keys=True))
PY
```

Do not overwrite an existing file. Rotation is a separate owner-approved
transaction with an overlap window and rollback; it is not this bootstrap.

## 2. Explicit owner-approved creation

Run only after the owner approves creation of this production credential. The
program creates the value on Home with `O_EXCL|O_NOFOLLOW`, fsyncs it and emits
only a sanitized metadata verdict. It never prints or returns the token.

```bash
ssh -o BatchMode=yes -o ConnectTimeout=8 "$REMOTE" /usr/bin/python3 - <<'PY'
import grp, json, os, pathlib, secrets, stat

parent = pathlib.Path("/etc/kolibri")
target = parent / "owner-api-token"
parent_value = parent.lstat()
if (
    not stat.S_ISDIR(parent_value.st_mode)
    or stat.S_ISLNK(parent_value.st_mode)
    or parent_value.st_uid != 0
    or parent_value.st_mode & 0o022
):
    raise SystemExit("owner_token_parent_unsafe")
if os.path.lexists(target):
    raise SystemExit("owner_token_already_exists")

gid = grp.getgrnam("kolibri-agent").gr_gid
flags = (
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    | getattr(os, "O_NOFOLLOW", 0)
)
descriptor = os.open(target, flags, 0o640)
try:
    os.fchmod(descriptor, 0o640)
    os.fchown(descriptor, 0, gid)
    os.write(descriptor, (secrets.token_urlsafe(48) + "\n").encode("ascii"))
    os.fsync(descriptor)
finally:
    os.close(descriptor)

value = target.lstat()
if (
    not stat.S_ISREG(value.st_mode)
    or stat.S_ISLNK(value.st_mode)
    or value.st_nlink != 1
    or value.st_uid != 0
    or value.st_gid != gid
    or stat.S_IMODE(value.st_mode) != 0o640
):
    raise SystemExit("owner_token_metadata_invalid")
print(json.dumps({
    "status": "created",
    "path": "/etc/kolibri/owner-api-token",
    "mode": "0640",
    "owner": "root",
    "group": "kolibri-agent",
    "secret_output": False,
}, sort_keys=True))
PY
```

## 3. Canonical backend drop-in

The drop-in contains no token value. Run its read-only plan first, then the
separate explicit apply. The apply backs up the old unit metadata, installs
only `10-release.conf`, restarts only `kolibri-backend.service`, checks health
and rolls the drop-in back if that restart fails.

```bash
BACKEND_RUN_ID="owner-token-backend-$(date -u +%Y%m%dT%H%M%SZ)"
scripts/bootstrap-home-backend-release.sh \
  --manifest "$MESH_MANIFEST" \
  --run-id "$BACKEND_RUN_ID"

scripts/bootstrap-home-backend-release.sh \
  --manifest "$MESH_MANIFEST" \
  --run-id "$BACKEND_RUN_ID" \
  --apply
```

Do not start Telegram as part of this step. Its service account, bot
credential, receiver ownership and duplicate-receiver fence are separate
gates. The canonical unit uses `SupplementaryGroups=kolibri-agent` and the
same token-file path; it never receives an inline owner token.

## 4. Post-restart protected API smoke without token output

Run the smoke on Home loopback so the bearer never crosses the network. The
program reads the value into process memory only, performs one authenticated
GET, discards the response body, and prints only the HTTP/status verdict.

```bash
ssh -o BatchMode=yes -o ConnectTimeout=8 "$REMOTE" /usr/bin/python3 - <<'PY'
import json, os, pathlib, stat, urllib.error, urllib.request

path = pathlib.Path("/etc/kolibri/owner-api-token")
descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
try:
    value = os.fstat(descriptor)
    if not stat.S_ISREG(value.st_mode) or stat.S_IMODE(value.st_mode) != 0o640:
        raise SystemExit("owner_token_metadata_invalid")
    token = os.read(descriptor, 4097).decode("utf-8").strip()
finally:
    os.close(descriptor)
if not token or len(token.encode("utf-8")) > 4096 or any(ch.isspace() for ch in token):
    raise SystemExit("owner_token_content_invalid")

request = urllib.request.Request(
    "http://127.0.0.1:8001/v1/projects",
    method="GET",
    headers={"Authorization": "Bearer " + token},
)
try:
    with urllib.request.urlopen(request, timeout=8) as response:
        status = response.status
        response.read()
except urllib.error.HTTPError as exc:
    status = exc.code
    exc.read()
if status != 200:
    raise SystemExit("owner_api_smoke_failed")
print(json.dumps({
    "status": "passed",
    "http_status": status,
    "endpoint": "/v1/projects",
    "secret_output": False,
}, sort_keys=True))
PY
```

Only after this returns HTTP `200`, the immutable exact-file-set preflight
passes, and signed rollback/candidate bundles are self-verified may the owner
approve the Home release task.

# P7 immutable paired release

`kolibri_p7_release.py` is a local builder and fail-closed release planner for
the P7 frontend/backend pair. It does **not** contain an apply command and
cannot change nginx, systemd, symlinks, a database, DNS, or a remote host.
`kolibri_p7_executor.py` is the separate root-only activation boundary. It
accepts only a canonical, signed, owner-approved P7 plan, repeats the planner's
signature/digest checks from private snapshots and rolls back automatically.
Building or planning never invokes this executor.

The older `kolibri_domain_api_cutover.py` remains unchanged. It is an r9-only
backend route tool and is not the P7 release path.

## Fixed P7 side-by-side targets

| Surface | Listener | Routes |
| --- | --- | --- |
| Backend | `127.0.0.1:18018` | `/api/v1/`, `/api/`, `/v1/`, `/ws/` |
| Frontend | `127.0.0.1:15194` | `/` |

Both products carry exactly the same release ID:

- backend runtime: `KOLIBRI_RELEASE_ID=<release-id>`;
- frontend build: `VITE_KOLIBRI_RELEASE_ID=<release-id>`;
- backend responses: `X-Kolibri-Release: <release-id>`.

The route plan always changes frontend and backend together in one complete
site configuration. A backend-only or frontend-only P7 switch is invalid.

## 1. Build from a clean commit

Use an output directory outside the Git worktree. The builder refuses tracked
or untracked changes, a detached non-commit source, a stale frontend build, an
existing output directory, symlinks, secret-like files and runtime data.

Unsigned local candidate:

```bash
python3 kolibri-backend/ops/release/kolibri_p7_release.py build \
  --repo "$PWD" \
  --output-root /var/tmp/kolibri-p7-candidates \
  --release-id kolibri-r17-20260714-p7
```

The output contains:

```text
source.bundle
backend.tar
frontend.tar
release-manifest.json
SHA256SUMS
```

`source.bundle` contains the exact committed HEAD. The canonical manifest binds
its SHA-256, both runtime archives, explicit ports/routes, the one release
identity and the P7 functional gates. It also records the exact Python, Node
and npm versions used by the builder plus SHA-256/size for every tracked
supported lockfile present. These are reproducibility evidence, not a claim
that a version is “latest”. The backend archive is built exclusively from
`git ls-files`; ignored `*.db`, SQLite sidecars and `*.schema.lock` runtime
state can never enter it.

The manifest also binds the required runtime secret names
`JWT_SECRET_KEY` and `KOLIBRI_EVIDENCE_SIGNING_KEY` plus a minimum of 32
bytes. Their values are forbidden from the manifest and release archives and
must be supplied by the protected runtime secret store during activation.

The tracked `kolibri-backend/requirements.lock` is a hash-locked Linux x86-64
resolution for Python 3.14. Regenerate it intentionally when
`requirements.txt` changes, then rebuild and sign a new candidate:

```bash
uv pip compile kolibri-backend/requirements.txt \
  --python-version 3.14 \
  --python-platform x86_64-unknown-linux-gnu \
  --generate-hashes \
  --no-strip-extras \
  --no-emit-package pip \
  --no-emit-package setuptools \
  --no-emit-package wheel \
  --custom-compile-command 'uv pip compile requirements.txt --python-version 3.14 --python-platform x86_64-unknown-linux-gnu --generate-hashes --no-strip-extras' \
  --output-file kolibri-backend/requirements.lock
```

The executor requires the runtime Python patch version to equal the signed
manifest and installs the lock with `pip --require-hashes --no-deps`. A stale,
missing, modified or incompatible lock fails before a listener is started.

## 2. Pinned trust roots and optional candidate signing

An unsigned candidate may be inspected locally, but it can never produce an
activation plan. Production trust is fixed by release-controller policy:

```text
/etc/kolibri/trust/p7-owner.allowed_signers
  identity: kolibri-owner

/etc/kolibri/trust/p7-gate-collector.allowed_signers
  identity: kolibri-p7-gate-collector
```

Both roots must be absolute, regular, root-owned and not group/world writable.
They and the signer identities are not CLI arguments, so a caller cannot
substitute an attacker-controlled `allowed_signers` file. To build a signed
candidate, supply only the owner-held OpenSSH private key:

```bash
python3 kolibri-backend/ops/release/kolibri_p7_release.py build \
  --repo "$PWD" \
  --output-root /var/tmp/kolibri-p7-candidates \
  --release-id kolibri-r17-20260714-p7 \
  --signing-key "$KOLIBRI_RELEASE_SIGNING_KEY"
```

The key bytes are never read by Python; the key path is passed to
`ssh-keygen -Y sign`. The builder immediately verifies the detached signature
with `ssh-keygen -Y verify` and namespace `kolibri-p7-release`. Missing tooling,
incomplete signing arguments, a bad signature or an unavailable public signer
file fail closed. Key paths and command stderr are not included in JSON output.

Offline verification:

```bash
python3 kolibri-backend/ops/release/kolibri_p7_release.py verify \
  --release-dir /var/tmp/kolibri-p7-candidates/kolibri-r17-20260714-p7 \
  --repo "$PWD" \
  --require-signature \
  --signature /var/tmp/kolibri-p7-candidates/kolibri-r17-20260714-p7/release-manifest.json.sig
```

## 3. P7 functional gate evidence

The release-specific collector must write canonical JSON with schema
`kolibri.p7.functional-gates.v3`, bind it to `release_id`, exact
`manifest_sha256`, backend/frontend origins and a unique collector run ID, then
sign it as `kolibri-p7-gate-collector` in namespace
`kolibri-p7-functional-gates`. All required results must be present. The gate
proves both the estimate reference vertical and the complete public product:

1. `release_identity` — frontend, backend body and response header agree;
2. `estimate_create_regional` — HTTP 201, individualized scope, no fixed
   template reuse, at least one evidence record and status `source_backed` or
   `verified`; `needs_input` and `preliminary` fail the release gate;
3. `estimate_recalculate` — server Decimal recalculation, version increment,
   changed total and persisted reload;
4. `estimate_revisions` — at least two revisions and an immutable previous
   revision;
5. `estimate_pdf` — HTTP 200, `application/pdf`, `%PDF-`, non-empty bytes and
   SHA-256.
6. `capability_registry` — dynamic backend registry, tri-state verdicts and
   release identity;
7. `chat_durable_stream` — delta stream, completion, cancellation, retry and
   persisted project history;
8. `web_search_sources` — a real provider call with dated HTTPS sources and a
   persisted result;
9. `file_lifecycle` — upload, analysis, search, byte-identical reopen and
   download;
10. `document_artifacts` — verified PDF, DOCX, XLSX and PPTX bytes;
11. `image_lifecycle` — real generation and edit with distinct, rendered,
    downloadable and reopenable raster bytes;
12. `site_app_lifecycle` — verified site/app ZIPs and sandbox previews;
13. `developer_api_keys` — create, one-time reveal, use, list without secret,
    revoke and reject;
14. `structured_apis` — Responses and Chat Completions streams, JSON schema
    output and the public `kolibri` model identity;
15. `shell_desktop_mobile` — desktop, tablet and both mobile viewports with no
    console, unexplained network or overflow defects and persisted artifact
    reopening;
16. `optional_capability_gates` — unavailable tools are hidden, degraded tools
    have technical reasons, external integrations are owner-gated, and no
    placeholder success is visible.

Validate a captured evidence file without contacting a server:

```bash
python3 kolibri-backend/ops/release/kolibri_p7_release.py verify-gates \
  --release-dir /var/tmp/kolibri-p7-candidates/kolibri-r17-20260714-p7 \
  --evidence /var/tmp/kolibri-p7-functional-gates.json \
  --signature /var/tmp/kolibri-p7-functional-gates.json.sig
```

The gate validator does not infer success from HTTP acceptance, a title, a
heartbeat or a PDF label. It requires a pinned-collector signature, exact
target binding, persisted lifecycle evidence and real byte hashes for every
artifact format.
Parsing, signature verification and SHA-256 binding all use one in-memory byte
snapshot; replacing the file path between those stages cannot mix two payloads.

## 4. Generate the non-mutating paired switch plan

The plan is bound to:

- the signed P7 manifest and pinned owner signer;
- a canonical owner approval signed in namespace
  `kolibri-p7-owner-approval`;
- the exact previous nginx site-config SHA-256;
- the exact signed rollback manifest, artifact hashes and prior release ID;
- collector-signed rollback health/release/route evidence;
- the collector-signed functional-gate evidence digest;
- both frontend/backend target route maps.

The signed approval JSON (`kolibri.p7.owner-approval.v1`) must bind the action,
approval ID, candidate release/manifest, functional-gate evidence SHA-256,
rollback release/manifest, rollback-health evidence SHA-256 and previous route
config SHA-256. A free-form approval ID is not authorization.

```bash
python3 kolibri-backend/ops/release/kolibri_p7_release.py plan-switch \
  --release-dir /var/tmp/kolibri-p7-candidates/kolibri-r17-20260714-p7 \
  --rollback-release-dir /secure/releases/p6 \
  --gate-evidence /var/tmp/kolibri-p7-functional-gates.json \
  --gate-evidence-signature /var/tmp/kolibri-p7-functional-gates.json.sig \
  --rollback-signature /secure/releases/p6/release-manifest.json.sig \
  --rollback-health-evidence /var/tmp/kolibri-p6-rollback-health.json \
  --rollback-health-signature /var/tmp/kolibri-p6-rollback-health.json.sig \
  --previous-route-config-sha256 '<64-hex-from-read-only-capture>' \
  --owner-approval /secure/approvals/p7-owner-approval.json \
  --owner-approval-signature /secure/approvals/p7-owner-approval.json.sig \
  --signature /var/tmp/kolibri-p7-candidates/kolibri-r17-20260714-p7/release-manifest.json.sig \
  --repo "$PWD" \
  > /var/tmp/kolibri-p7-paired-switch-plan.json
```

The plan explicitly requires one candidate config, one atomic config-file
replacement and one reload. Any direct-health, release-identity, route,
estimate, revision or PDF failure triggers restoration of the byte-for-byte
saved config followed by rollback release/health/route verification. A
rollback directory with a missing/bad owner signature, mismatched artifact,
stale release identity, failed health probe or incomplete route matrix is
rejected before planning.

Generating the plan does not authorize or perform the switch.

## 5. Root-only signed execution

Execution is a separate, explicit owner-controlled operation. Before running,
capture the exact active nginx SHA used by the signed plan, identify the exact
P6 backend unit, and place runtime secrets in a root-protected regular file.
Do not pass secret values on the command line.

```bash
sudo python3 kolibri-backend/ops/release/kolibri_p7_executor.py \
  --plan /secure/plans/kolibri-p7-paired-switch-plan.json \
  --release-dir /secure/releases/kolibri-r17-20260714-p7 \
  --release-signature /secure/releases/kolibri-r17-20260714-p7/release-manifest.json.sig \
  --rollback-release-dir /secure/releases/p6 \
  --rollback-signature /secure/releases/p6/release-manifest.json.sig \
  --gate-evidence /secure/evidence/kolibri-p7-functional-gates.json \
  --gate-evidence-signature /secure/evidence/kolibri-p7-functional-gates.json.sig \
  --rollback-health-evidence /secure/evidence/kolibri-p6-rollback-health.json \
  --rollback-health-signature /secure/evidence/kolibri-p6-rollback-health.json.sig \
  --owner-approval /secure/approvals/p7-owner-approval.json \
  --owner-approval-signature /secure/approvals/p7-owner-approval.json.sig \
  --previous-backend-service kolibri-backend-p6.service \
  --runtime-secret-file /etc/kolibri/backend.env \
  --python-binary /usr/bin/python3
```

The executor performs this fail-closed sequence under an exclusive lock:

1. privately snapshots the plan, both release bundles, signatures, approval
   and evidence using regular-file/no-symlink checks;
2. calls `paired_switch_plan` again and requires exact canonical plan equality;
3. verifies signed artifact targets `18018/15194`, lock hash and active nginx
   SHA before any live mutation;
4. extracts archives without links, devices or path traversal and installs the
   hash-locked Python environment; the immutable payload remains root-owned
   and readable while mutable data is owned by the configured runtime account;
5. installs fixed hardened P7 units, stops the exact P6 writer, proves an
   exclusive SQLite write drain, takes an online backup and migrates only the
   copy through revisions `007`, `008` and exact head `009_document_scope`;
6. starts both loopback listeners side-by-side and proves the exact release ID
   directly on backend and frontend;
7. renders one complete candidate site, runs isolated `nginx -t`, rechecks the
   live SHA against TOCTOU drift, atomically replaces exactly one site file,
   runs final `nginx -t`, and reloads nginx exactly once;
8. proves public frontend/backend identity, JSON 404 behavior and atomic shell
   bootstrap. The already collector-signed estimate/revision/PDF functional
   gates remain bound by digest to the reverified plan.

If any step fails, the executor restores the exact saved P6 nginx bytes,
restarts and verifies the exact P6 backend before reloading the restored route,
stops any partially started candidate, restores previous unit files and checks
the public P6 identity. A rollback defect is reported as
`p7_automatic_rollback_failed`; it is never converted into success. Canonical
execution evidence is written under `/var/lib/kolibri/release-evidence/p7/` and
contains hashes/status codes, never secret values or subprocess output.

The executor does not modify DNS, REG.RU, firewall rules, remote servers or
the source repository. It does not provide an unsigned, force or skip-gates
mode.

The fixed candidate units must be inactive and disabled before activation, and
the explicitly named previous backend unit may not be the P7 candidate unit.
This prevents an attempted rollback from disabling or overwriting an unrelated
already-running release.

## Test

```bash
python3 -m pytest -q \
  kolibri-backend/ops/release/tests/test_kolibri_p7_release.py \
  kolibri-backend/ops/release/tests/test_kolibri_p7_executor.py \
  kolibri-backend/ops/release/tests/test_kolibri_p7_migrate.py \
  kolibri-backend/ops/release/tests/test_kolibri_p7_static_server.py
```

The suite creates isolated owner and collector Ed25519 trust roots and exercises
real OpenSSH signing/verification where `ssh-keygen` is available. It proves
caller-supplied trust roots, dirty source, artifact tamper, signature tamper,
unsigned/target-mismatched gate evidence, preliminary estimates, unbound
approval, bad rollback health and unsigned-plan paths are rejected.
Executor tests use temporary filesystems and fake command runners. They prove
route-drift rejection, safe extraction, write-drain backup, exact migration
head, runtime secret/Python gates, partial-start cleanup, single reload,
public post-gates and byte-for-byte automatic P6 rollback without touching a
live service.

# Deterministic release bundle builder

Status: implementation contract, 2026-07-11. Building a local bundle is not a
production rollout or owner approval.

`ops/release_bundle_builder.py` is the only canonical producer for
`kolibri.release.v1` archives consumed by `ops/release_installer.py`.

## Safety model

- The default invocation validates the selected payload and prints a plan. It
  does not create an output archive or access a signing key.
- A final archive requires both `--build` and `--sign`, plus an explicit key
  path and signer identity.
- Python never reads private-key bytes. The path is passed only to
  `ssh-keygen`; command output is discarded and the path is omitted from all
  result and error JSON.
- Existing output is never overwritten. The verified temporary archive is
  published atomically without replacement.
- `venv`, `.venv`, `node_modules`, `__pycache__`, cache directories, secrets,
  private files and runtime data are excluded. Explicit selection of a secret
  or symlink fails closed.

## Payload profile

The default payload includes:

- backend Python, JSON and `requirements*` files, excluding backend tests and
  runtime data;
- every regular file under `frontend/dist`;
- optional repository-relative files or directories supplied with repeatable
  `--runtime-path` arguments.

File paths are sorted. Files are hashed through no-follow descriptors and
bound by SHA-256, size and normalized safe mode. A source mutation between
planning and archive construction aborts the build.

## Usage

Read-only plan:

```bash
python3 ops/release_bundle_builder.py \
  --release-id kolibri-2026.07.11-rc1 \
  --source-commit 0123456789abcdef \
  --runtime-path ops/agent_host.py \
  --runtime-path ops/release_installer.py
```

Explicit local build and detached signature:

```bash
python3 ops/release_bundle_builder.py \
  --release-id kolibri-2026.07.11-rc1 \
  --source-commit 0123456789abcdef \
  --artifact-uri artifact://bundles/kolibri-2026.07.11-rc1.tar.gz \
  --output release/bundles/kolibri-2026.07.11-rc1.tar.gz \
  --runtime-path ops/agent_host.py \
  --runtime-path ops/release_installer.py \
  --build --sign \
  --signer-identity owner-release \
  --signing-key /secure/path/release_signing_key
```

The final archive has only this layout:

```text
.kolibri-release/manifest.json
.kolibri-release/manifest.sig
payload/<manifest file path>
```

The manifest uses canonical compact sorted-key UTF-8 JSON. Tar member order,
ownership, timestamps and gzip timestamp are deterministic. Before atomic
publication, the builder reuses the installer extraction, canonical manifest,
sshsig (`kolibri-release`) and payload verification code against an ephemeral
allowed-signers snapshot derived from the supplied key's public half.

The builder does not create a Control Plane task, owner approval attestation,
rollout wave or production claim. Those remain release-controller concerns.

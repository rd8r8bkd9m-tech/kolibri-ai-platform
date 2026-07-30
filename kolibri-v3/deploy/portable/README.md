# Kolibri V3 portable production release

This package installs one isolated Kolibri V3 instance on a Linux host with
systemd. It never copies credentials into a release and does not modify another
Kolibri instance when a unique `KOLIBRI_INSTANCE`, install root, and ports are
used.

## Host requirements

- Linux with systemd, Bash, curl, tar, git, and `flock`
- Python 3 with `venv`
- Node.js 20 or newer and npm
- an existing non-root service account
- Codex CLI authenticated as that service account when the direct agent runtime
  is enabled
- a healthy MiMo runtime owned by this deployment when `KOLIBRI_REQUIRE_MIMO`
  is enabled
- optional Nginx and an existing TLS certificate

## Build the canonical immutable V3 archive

Run this only from a clean committed V3 tree:

```bash
./deploy/portable/build-release.sh
```

The builder reads the committed `kolibri-v3` Git tree rather than copying the
working directory. It fails when that tree has tracked or untracked changes.
Before reading the V3 subtree, it audits the complete source commit and fails
if a parent-level V3 Home/Primary/bare-metal release helper is present. The
retired parent coordinator is accepted only as its byte-exact read-only
tombstone; any changed or executable deployment implementation is rejected.
The release ID binds the exact Git commit and a path-stable SHA-256 content
digest. The archive contains both `app/` and `backend/`, plus:

- `RELEASE_CONTENTS.sha256`, using paths relative to `kolibri-v3`;
- `MIGRATIONS.sha256`, with every ordered SQL migration digest;
- `RELEASE_PROVENANCE.json`, with the release identity, commit, tree, gate
  input digest, migration range, deterministic build timestamp, and toolchain.

The adjacent `.manifest.json` records the package SHA-256 (which cannot be
self-embedded in the package it hashes), and the `.sha256` file supports a
standard transfer check. Copy all three files to the target host.

`deploy/portable` is the only V3 production release lane. The archive builder
fails closed if an obsolete installer, static production unit, legacy backend,
contract manifest that does not match the packaged schemas, private-key
material, or a recognized provider/cloud access token is present. Credential
file names such as `.npmrc`, `.netrc`, `.pypirc`, SSH identities, service
account JSON, mobile signing profiles, P8/PFX and Java keystores are forbidden.
The content scan covers private-key blocks, credential assignments, registry
auth, cloud account keys, authenticated URLs, JWTs, and common OpenAI,
Anthropic, GitHub, GitLab, Slack, npm, Stripe, Google, DigitalOcean, Hugging
Face, Telegram and AWS token formats. Synthetic examples in tests must be
constructed without embedding a token-shaped literal; never weaken the scan
or exclude test directories to make a package pass.

## Install

```bash
cp deploy/portable/config.env.example deploy/portable/config.env
# Edit the instance, service user, domain, paths, ports, and TLS certificate.
sudo ./deploy/portable/install.sh \
  ./deploy/portable/config.env \
  /absolute/path/kolibri-v3-<commit>-<content-digest>.tar.gz
```

Keep the archive's `.manifest.json` and `.sha256` sidecars beside it. The
installer opens all three as trusted file descriptors, verifies the checksum,
every packaged file, Git provenance, and migration range, and extracts from the
same already-open archive. Its local `install.sh`, `install-contract.py`, and
`release-manifest.py` must byte-match the verified copies in the package.

The config is a strict `KEY=value` file, not a shell script. It must be a
canonical regular file owned by root or the invoking sudo user and must not be
group- or world-writable.

To validate the host, agent credentials, MiMo, Nginx, and TLS without changing
the server:

```bash
sudo KOLIBRI_PREFLIGHT_ONLY=true \
  ./deploy/portable/install.sh \
  ./deploy/portable/config.env \
  /absolute/path/kolibri-v3-<commit>-<content-digest>.tar.gz
```

The installer builds and tests in a private staging directory, re-verifies the
already-open archive after dependency/build scripts, and rehydrates the backend
from that clean verified source rather than trusting a mutable build tree. It
then freezes the complete release as root-owned read-only content and atomically promotes it below
`releases/<release-id>`, and only then changes the `current` symlink. It binds
both application processes to loopback, installs instance-specific systemd
units, backs up the SQLite database, and rolls back the symlink, units,
configuration, reverse proxy, and previous durable-worker state if a health
gate fails.

The persistent database and CSRF secret live below `KOLIBRI_INSTALL_ROOT/var`;
they are not stored inside a release.

Before migration or activation, the installer now creates the SQLite backup
through the packaged `database-rehearsal.py` helper. The helper uses SQLite's
online backup API, verifies `integrity_check` and foreign keys, writes mode
`0600`, and publishes the backup atomically without overwriting an existing
artifact.

`KOLIBRI_CONFIG_ROOT/backend.env` is operator-owned, root-owned mode `0600`,
and is never overwritten during a successful activation. Put optional agent,
provider, and model-runtime configuration there. The embedded local developer
adapter is forbidden in production: preflight rejects
`KOLIBRI_V3_DEVELOPER_AGENT_ENABLED=true` (including the equivalent
`1/yes/on` values). Production developer execution must use the isolated
Home/Provider worker plane. The installer writes a
separate root-owned mode-`0600` `release.env` after it in systemd precedence;
that managed file contains the canonical production database, public origin,
CSRF/security state, release ID, and exact Git commit. Frontend health at
`/api/health` must report that exact ID and commit before activation succeeds.

Before any background worker is activated, the host installer must converge the
canonical database and any existing `-wal`/`-shm` sidecars to the service
account owner with mode `0600`. The backend systemd unit must use
`UMask=0077`, so sidecars created later inherit the same private policy. Worker
preflight deliberately fails closed until these conditions hold; never weaken
that ownership/mode gate to accommodate a host.

The Product worker is mandatory for a production release. The installer
rejects `KOLIBRI_ENABLE_PRODUCT_WORKER=false` and requires the non-secret
endpoint values in `KOLIBRI_CONFIG_ROOT/workers.env` plus its systemd
credential files below `KOLIBRI_CONFIG_ROOT/credentials`. The provider
enrollment worker remains optional. The installer validates enabled-worker
inputs before the switch and again before start; each unit then runs
`worker_launcher.py ... --check` as `ExecStartPre`. The reconciliation audit is
installed but never started automatically. Final installer output reports each
worker as `enabled_active` or `disabled_by_configuration`.

The managed release environment also binds
`KOLIBRI_V3_DIRECT_MODEL_RUNTIME` to the host-gated release profile and requires
a fresh, exact-release Product worker heartbeat. Backend `/v1/health` proves
the database schema and release identity; `/v1/ready` additionally proves the
mandatory execution boundary. The frontend and public `/readyz` consume the
full readiness endpoint, so an idle or wrong-release worker cannot produce a
green activation.

The installer also creates two independent systemd timer lanes:

- `${KOLIBRI_INSTANCE}-release-monitor.timer` runs every minute and fails the
  oneshot service when the exact backend, frontend, public release, mandatory
  Product worker, database, backup, disk, TLS or error-rate contract is not
  healthy;
- `${KOLIBRI_INSTANCE}-database-backup.timer` creates a verified online SQLite
  backup every day. A failed backup unit immediately triggers the release
  monitor, and stale or invalid backup evidence remains an alert until a fresh
  verified snapshot exists.

The monitor reads aggregate structured HTTP events and the durable queue
state. Its single JSON result contains only the release identity, bounded alert
codes, request/error counts, p95 latency, queue depths, running/stuck run
counts, available bytes, backup age and TLS lifetime. It never emits URLs,
paths, database rows, prompts, cookies or credentials. Exit status `2` means an
operational alert; invalid monitor configuration exits `3`. systemd/journald is
the canonical local alert stream and may be forwarded by the host collector
without giving notification credentials to the public application.

The packaged public check uses the configured HTTPS hostname, including DNS,
the public readiness body and the certificate served to the host. The later
canary still requires an independent cellular/external vantage point; a
self-monitor cannot prove the route from every outside network.

This externalizes privileged developer capability from the public backend; it
does not remove it or hand it to a third party. Kolibri's own supervised Agent
Host is the first-class operations plane for the in-app flow: tasks lead to
code/UI/server changes, gates and deployment, then notifications, diffs, and
rollback evidence. An owner-configured trusted-agent profile may use
`danger-full-access` with `approval=never` inside its isolated Agent Host
workspace. The public V3 backend never hosts that adapter.

The lane remains explicit and repeatable: the product worker flag, endpoint
configuration, and credentials are validated on every install, while
operator-owned files are preserved. The installer does not silently enable the
lane. Its output reports the worker activation state,
`trusted_agent_plane=kolibri_agent_host`, and
`developer_execution=externalized_home_provider_worker_plane`.

## Pre-deployment smoke test

This first verifies the archive, package checksum, provenance, canonical V3
backend/web roots, and every file and migration digest. It then performs a
clean dependency install and production build with the exact release identity,
starts the standalone frontend, backend and mandatory Product worker under
`KOLIBRI_V3_ENV=production`, and checks full readiness plus the
`X-Kolibri-Release` response header using a temporary database and isolated
ports:

```bash
./deploy/portable/smoke-test.sh \
  /absolute/path/kolibri-v3-<commit>-<content-digest>.tar.gz
```

Smoke testing never uses the live database. Database migrations in portable
releases must be expand/additive because activation rollback changes code and
services but does not reverse a migrated production database.

## Database restore rehearsal

Run this against a production-like copy before owner GO. The source database
is opened for an online backup and is never modified. The helper restores the
snapshot into a separate database, verifies its exact SHA-256, schema version,
integrity and foreign keys, then performs a real write inside an immediate
transaction and proves that the probe rolls back cleanly:

```bash
install -d -m 0700 /absolute/private/rehearsal
python3 deploy/portable/database-rehearsal.py rehearse \
  --source /absolute/path/kolibri-v3.db \
  --work-dir /absolute/private/rehearsal \
  --expected-version 43
```

The work directory must be canonical, private and empty of the two fixed
rehearsal artifacts. Preserve the printed snapshot SHA-256 in release
evidence; never copy the database itself into the repository.

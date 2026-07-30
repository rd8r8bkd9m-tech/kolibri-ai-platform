# Kolibri V3 background worker deployment

These templates cover the three current V3 background entry points while
keeping `/etc/kolibri-v3/backend.env` and its exact
`KOLIBRI_V3_DATABASE_URL` as the single database authority.

## Safety decision

| Entry point | Ownership in code | Deployment decision |
| --- | --- | --- |
| `app.product_run_worker` | Atomic SQLite claim, expiring lease, unique lease token and monotonic fencing token; every state mutation re-checks ownership | Safe to enable after Product Authority and Logical Home transport preflight passes |
| `app.provider_enrollment_worker` | Atomic SQLite claim, expiring lease, unique lease token and monotonic fencing token; stale completions are ignored | Safe to enable after Provider Authority dispatch is explicitly enabled and its transport preflight passes |
| `app.estimate_reconciliation` | No durable job row, lease owner or fencing token around `--apply` | **Apply mode is blocked.** Only the included logically read-only audit service is safe to run |

The launcher adds one non-blocking local `flock` per role. This catches a
duplicated unit on the same host. Correctness for the two durable workers still
comes from their database leases; the local lock is not described as a
distributed lock.

The reconciliation launcher has no command that can append `--apply`.
Creating a mutating recurring service is blocked until reconciliation owns a
durable database job with a lease token, fencing token, expiry, and idempotent
terminal transition. An operator can still run the existing command manually
during an approved maintenance window, but this directory does not automate
that unsafe path.

## Template values

Render every `.service.in` file before installation:

- `@INSTALL_ROOT@`: canonical V3 root, currently `/opt/kolibri-v3`
- `@CONFIG_ROOT@`: canonical config root, currently `/etc/kolibri-v3`
- `@SERVICE_USER@` and `@SERVICE_GROUP@`: the same account as the backend
- `@BACKEND_SERVICE@`: the rendered backend unit, currently
  `kolibri-v3-backend.service`

Install `worker_launcher.py` as the root-owned, non-writable executable
`@INSTALL_ROOT@/libexec/worker_launcher.py`. The stable libexec location is
intentional: both current release layouts expose `current/backend`, but neither
guarantees a `current/deploy` directory. Replace the launcher atomically
together with its rendered units.

Do not render two different V3 deployments against the same SQLite file.
SQLite, its WAL/SHM files, and the migration lock all live in
`@INSTALL_ROOT@/var`; therefore the sandbox grants that directory (not just
the `.db` file) write access.

## Required configuration

1. Keep the canonical database URL in `backend.env`. The launcher rejects a
   default, relative, missing, symlinked, foreign-owned, or differently named
   database. The database and any existing `-wal`/`-shm` sidecars must be
   owned by the backend account and mode `0600`; a world-readable identity/chat
   database fails preflight. The backend unit must use `UMask=0077` so later
   sidecars keep that policy. Until the release installer enforces those modes,
   permission normalization is an explicit activation prerequisite, not an
   automatic launcher mutation.

   On an existing install, apply the permission change only in a maintenance
   window: stop backend/workers, add `UMask=0077` to the backend unit, set the
   explicit database and each present `kolibri-v3.db-wal` /
   `kolibri-v3.db-shm` file to `0600`, then restart the backend and re-run the
   audit. This avoids racing SQLite while it creates or replaces a sidecar.
2. Copy `workers.env.example` to `workers.env`, mode `0600`, and fill the exact
   dispatch URLs. HTTP is accepted by application validation only for
   loopback; remote authorities require HTTPS.
3. Set
   `KOLIBRI_V3_PROVIDER_AUTHORITY_DISPATCH_CONFIGURED=true` only after the
   corresponding Primary endpoint is ready. Preflight also requires the
   provider lease to exceed its HTTP request timeout by at least one second,
   preventing a configured request from outliving local ownership.
4. Create root-owned, mode `0600` credential source files:

   - `credentials/home-product-command-token`
   - `credentials/home-product-identity-hmac-key`
   - `credentials/provider-authority-command-token`
   - `credentials/provider-authority-identity-hmac-key`

   `LoadCredential=` gives each worker a private read-only copy. Do not also
   define the direct Product token/key variables in `backend.env`; the
   application deliberately rejects simultaneous direct and file sources.

The common `Settings.from_env()` validation still applies. In production this
includes the secure cookie/CSRF settings, explicit HTTPS origins, and the
complete Product Authority grant already used by the backend.

## Activation and verification

Before activation:

1. Render the templates to a temporary directory and run
   `systemd-analyze verify` on all three rendered units.
2. Install the rendered units atomically under `/etc/systemd/system`, then run
   `systemctl daemon-reload`.
3. Start (but do not enable) one durable worker at a time. Its
   `ExecStartPre=... --check` validates the canonical DB and dispatch secrets
   without claiming a job.
4. Verify `systemctl status`, the worker journal, and the outbox transitions.
   A configuration failure exits `78`; duplicate local ownership exits `75`.
   Both are excluded from automatic restart.
5. Only after the queue smoke test is clean, enable the product and provider
   workers. Their `PartOf=` relation keeps them on the backend release
   lifecycle.

The reconciliation audit is an operator-run oneshot and has no `[Install]`
section. It uses `PrivateNetwork=true`, opens both diagnostic connections with
SQLite URI `mode=ro`, and never passes `--apply`. Its filesystem sandbox still
allows the database directory because a live WAL database may need SQLite
shared-memory coordination; this does not grant an application-level write
transaction. The JSON includes an identifier-free release gate for stale
`chat_runs`, grouped by `standard`/`developer` execution mode and outbox state,
plus the total blocked Product outbox. The default stale threshold is one hour
and can be tightened with `KOLIBRI_WORKER_STALE_RUN_SECONDS` (60–86400).

Treat `runtime.gate=blocked` (or service exit `65`) as a release blocker. Do
not enable the durable workers until every stale running row has been
explicitly reconciled to a terminal state and the audit returns `gate=pass`.
The audit only reports; it never repairs, deletes, or retries a row.

Rollback is simply: disable/stop the two worker units and remove their unit
files. No schema or queued command is deleted; expired durable leases can be
claimed after the corrected deployment starts.

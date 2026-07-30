# Local release observability and scheduled-backup gate — 2026-07-30

Captured: 2026-07-30 18:58 MSK

Scope: local V3 source, tests and an isolated clean synthetic commit.
Production, Home, Primary, Nginx, DNS and public traffic were not changed.
This evidence does not claim a frozen RC, remote CI, a deployed alert or a
production canary.

## Fail-closed runtime monitor

The packaged backend now includes `app.release_monitor`. One bounded JSON
record reports only the release ID/commit, timestamp, safe alert codes and
aggregate metrics. It does not return URLs, filesystem paths, prompts,
cookies, tokens, credentials or database rows.

The monitor verifies:

- exact backend, frontend and public release readiness;
- backend, frontend and Product worker systemd state;
- the last database-backup unit result;
- SQLite quick-check and the exact expected schema;
- stuck chat runs and both Product/direct queue depths;
- host free capacity and the freshness, ownership, mode and integrity of the
  latest private backup;
- the served public TLS certificate lifetime;
- bounded journald request count, 5xx rate and p95 latency.

The negative regression covers `public_down`, `backend_not_ready`,
`frontend_not_ready`, `backend_stopped`, `frontend_stopped`,
`product_worker_stopped`, `database_backup_job_failed`,
`database_backup_missing`, `database_backup_invalid`,
`database_backup_stale`, `database_check_failed`,
`database_schema_mismatch`, `stuck_runs`, `disk_space_low`,
`tls_certificate_invalid`, `tls_expiring`,
`error_metrics_unavailable` and `error_rate_spike`.

Exit `0` means healthy, `2` means an alert is active, and `3` means the
monitor configuration or its own execution failed closed.

## One renderer for installer and Linux CI

`install-contract.py render-operations` now generates the exact four
production files consumed by the installer:

```text
kolibri-v3-release-monitor.service
kolibri-v3-release-monitor.timer
kolibri-v3-database-backup.service
kolibri-v3-database-backup.timer
```

The renderer validates the instance, ports, HTTPS public origin, exact release
identity, schema, absolute paths and output directory before atomically writing
mode-0644 files. The monitor runs every minute. The backup runs daily through
the packaged online SQLite backup helper, uses a private root-owned target,
verifies the snapshot and triggers the release monitor when the oneshot fails.
Neither oneshot uses `Requires=` on the service it observes: a stopped backend,
frontend or worker cannot prevent the monitor from running or cause the
monitor itself to restart the failed component.

The portable installer no longer carries a second inline copy of these units.
It stores the rendered bytes in immutable release host assets, installs those
same bytes, runs `systemd-analyze verify`, performs one verified backup, runs
one monitor check, and enables the two timers only before declaring the switch
complete. Rollback restores the previous files and their previous
enablement/activity.

The Linux GitHub workflow now:

1. runs the monitor, migration, launch and portable regressions explicitly;
2. renders the four operation units with the production renderer;
3. creates only the three dependency stubs needed for static resolution;
4. runs `systemd-analyze verify` on the rendered monitor/backup units;
5. then builds, verifies and smokes the immutable archive.

The local macOS host has no `systemd-analyze`; therefore the Linux verification
is correctly recorded as a pending remote CI gate, not as a local pass.

## Local gates

```text
backend complete suite                     280 passed
web/contracts complete suite               128 passed
worker launcher                             19 passed
monitor + development preflight             13 passed
portable/startup/observability focused       24 passed
TypeScript                                  passed
production Next.js build                    passed
shell/Python syntax and scoped diff-check   passed
workflow YAML parse                         passed
```

An import-order regression exposed by the isolated identity suite was also
fixed: the `chat` package no longer eagerly imports its router while the direct
runtime is partially initialized. Identity tests pass independently at
`15 passed`; no authentication route or application composition API changed.

## Clean packaged smoke

An isolated repository was populated from the current V3 working tree while
excluding environment files, databases, dependencies, build output, caches
and runtime state. Its clean synthetic commit produced:

```text
preview_commit=ad9b1df3e0938743c1b32651e00301417b439a9a
release_id=kolibri-v3-ad9b1df3e093-192dc6697b8d
release_sha256=f84da49b434242ad47074e878a93566b11656db60d0dd686bdf06d45df515927
release_content_digest=192dc6697b8d9dab7b4e847549b1a4edb7fbe566abf8ca72c0770d11dd224418
release_gate_input_digest=e8334016e9651837e21f1832750719c2c268cf3a24d96567daa320ea2f93601c
release_migration_min=001
release_migration_max=044
release_verify=ok
smoke_status=ok
```

The archive contained the release monitor, database helper and shared unit
renderer. The smoke installed fresh dependencies (`0 vulnerabilities`), ran
all `128` web/contracts tests and typecheck, produced the standalone frontend,
migrated a fresh schema-44 database, started the real Product worker launcher,
and required the same release ID/commit from backend, worker and frontend.

The final 68 MiB preview and the superseded 68 MiB pre-fix preview were moved
to the user's Trash after evidence capture. They remain recoverable and will
consume disk until the Trash is emptied. Neither working-tree proof was
pushed, deployed or designated as the authorized release candidate.

## Remaining release gates

R1-009 remains `ACTIVE`. The following evidence is still required:

- remote Linux CI green on a clean committed revision, including
  `systemd-analyze verify`;
- an independent external/cellular public-down canary rather than only the
  on-host monitor;
- live alert delivery/acknowledgement evidence;
- final immutable-candidate smoke after freeze;
- canary deployment, rollback proof and explicit owner GO.

# Local owner, migration and release-identity gate — 2026-07-30

Scope: canonical local V3 runtime and isolated portable-package preview.
Production, Home, Primary, Nginx and DNS were not changed.

## Canonical restart and owner access

The only supported local entrypoint, `npm run dev`, was stopped and started
twice after the launcher change. On both starts the backend preflight completed
before Uvicorn opened port `8002`:

```text
Kolibri V3 preflight: schema=44 users=7 platform_owner=1
```

The launcher is pinned to `kolibri-v3/var/kolibri-v3.db`. Preflight now also
fails closed unless the singleton platform owner is the locally configured
`montodays@ya.ru` account, its password credential has the current
`scrypt-v1` structure, and both account and tenant access are active. It still
applies every ordered SQL migration before these checks.

The live database reported:

```text
PRAGMA user_version = 44
PRAGMA integrity_check = ok
foreign-key violations = 0
matching owner records = 1
active owner sessions = 6
login throttle = absent
```

The initial restart preserved the existing authenticated session as
`Суперадминистратор`.

Runtime probes:

```text
GET http://127.0.0.1:8002/v1/health = 200
GET http://127.0.0.1:8002/v1/ready = 200
GET http://127.0.0.1:3103/api/health = 200
GET http://127.0.0.1:3103/app = 200
```

## Owner credential recovery and wrong-directory protection

The current owner hash differed from the snapshot captured immediately before
the 2026-07-29 password override. Before changing it, SQLite created and
integrity-checked:

```text
var/backups/kolibri-v3-pre-owner-credential-restore-20260730-1749.db
```

Only the `password_hash` for the single `montodays@ya.ru` owner row was restored
from `var/backups/kolibri-v3-pre-owner-password-override-20260729.db`. No
password, hash value, session token or other credential was printed. The
account and tenant remain active, the unique `platform_owner` grant remains
active, six existing owner sessions remain valid, and the exact owner's login
throttle row was removed.

The default database URL is now derived from the V3 source root rather than
the process working directory. A read-only probe launched from `backend/`
resolved the same canonical database:

```text
/Users/kolibri/Documents/Codex/kolibri-ai-platform/kolibri-v3/var/kolibri-v3.db
```

The supervised backend was then terminated independently. The supervisor
fenced the web child, repeated:

```text
Kolibri V3 preflight: schema=44 users=7 platform_owner=1
```

and replaced backend PID `12192` with PID `12297` before starting the web child.
This verifies the migration and exact owner gate on automatic recovery, not
only on a clean manual launch.

## Exact release identity

Production backend health now requires and returns a bounded exact
`KOLIBRI_RELEASE_ID` plus lowercase 40-character
`KOLIBRI_RELEASE_COMMIT`. Missing or malformed identity returns 503.

Frontend readiness compares both values with backend health. A healthy backend
from another release, a missing identity or a commit mismatch returns 503.
The installer checks exact backend identity before starting frontend, checks
frontend identity before activation, and every durable worker validates the
same managed release environment before dispatch.

An isolated clean synthetic commit of the current working-tree candidate passed
the complete portable smoke:

```text
preview_commit=f98cfe4582c12121491e116617018294aa684cd5
preview_files=761
release_id=kolibri-v3-f98cfe4582c1-ac15fc725219
release_sha256=f112f1dbab0d8ce02e183c86a10db6e18998e6c3c6c511d378665db5eaef2535
release_content_digest=ac15fc725219a33c0855e9c0d6669cb09659486633679a6519cfe102c1dee699
release_gate_input_digest=2b9aed92e47f78cc8177847c7643c711e27a91d4fea382f204951e73e2aaa896
release_lane=canonical-portable-only
release_migration_min=001
release_migration_max=043
smoke_status=ok
```

The historical smoke installed dependencies into a disposable tree, ran
typecheck, all web/contracts tests, the optimized production build, a fresh schema-43
database, and exact backend plus frontend release-health probes. The synthetic
archive and both temporary preview directories were removed after recording
the evidence (58 MiB total). This was not a production RC and was not pushed.

## Schema-44 production-package smoke

A new isolated repository was created from the current V3 working tree without
local databases, environment files, dependency directories, build caches or
runtime state. Its final clean synthetic commit produced:

```text
preview_commit=fb732ee4eec49b8d83c9841a30df41f59b753c03
preview_files=796
release_id=kolibri-v3-fb732ee4eec4-7dbd6b22cebd
release_sha256=119ea2ad42850c8b0a20aff7603bd20547e1f3328797052188c247a8d121b0c7
release_content_digest=7dbd6b22cebd78b8cd427c2afd5be044791086ca2953d9d4349fc2b7a812ca11
release_gate_input_digest=424183ae7d67d2c4e6a7bd1635316d9848674b8c37ee1974fa82fd1bed01450d
release_lane=canonical-portable-only
release_migration_min=001
release_migration_max=044
smoke_status=ok
```

The first schema-44 attempt exposed that the smoke harness bypassed the
production worker launcher and started the module from the wrong import root.
The package did contain the worker, but the harness could not import it. The
smoke now starts `deploy/workers/worker_launcher.py product-run` from the
packaged backend working directory. This exercises the same allowlist,
canonical database ownership/mode checks, singleton lock, runtime validation
and exact release identity used by the systemd unit.

The next fail-closed attempt rejected macOS's `/var` temporary-directory alias
as `canonical_database_unsafe`. The worker invariant was retained. Instead,
the smoke workspace is canonicalized with `pwd -P` before the database URL and
lock path are constructed.

The final run:

- verified the archive, adjacent checksum and provenance;
- installed Python and Node dependencies into an empty extracted tree;
- reported `0 vulnerabilities` from the web dependency install;
- passed TypeScript and all `125/125` web/contract tests;
- produced the optimized standalone production build with the exact release
  ID and commit;
- created and migrated an isolated SQLite database through migration `044`;
- started the production backend and the real Product worker launcher;
- required a fresh exact-release Product worker heartbeat before `/v1/ready`
  returned success;
- started the standalone frontend and verified `/app`,
  `X-Kolibri-Release`, `/api/health`, and the anonymous session path.

No live database, production service, Home, Primary, Nginx or DNS state was
read or changed. The three synthetic preview trees totalled 204 MiB and were
moved to the user's Trash after evidence capture. The resulting archive was a
working-tree proof only, not an authorized immutable RC.

## Expanded archive secret scan

The archive scanner now rejects common credential files and mobile signing
material in addition to database, environment and private-key files. Content
signatures cover credential assignments, registry auth, cloud account keys,
authenticated URLs, JWTs and common provider token families.

Regression fixtures prove fail-closed rejection for `.npmrc`, Apple P8 signing
material, Slack-shaped tokens, assigned npm credentials and authenticated URLs.
The first full-tree scan correctly exposed an intentionally invalid
eight-character localhost basic-auth URL in a negative backend test. The
authenticated-URL signature was calibrated to require a 16-character
credential; test directories were not excluded from scanning.

After calibration, the complete current V3 tree produced and verified:

```text
preview_commit=622ba8eeb2cb33ceb74f168eaf63957060ba133c
release_id=kolibri-v3-622ba8eeb2cb-0cb9b828335a
release_sha256=ecfc19e29875cefaeb93565635357a0db0f82df7cb2d66191c4e2d225a0305a8
release_content_digest=0cb9b828335a1289d5c9144f39f6e65616aff8600603968e57d31e6c33d4e7f2
release_gate_input_digest=f8ad937d635112b80e9a2b513b008d72a94c7d10e5acc3203e669e67542dfc0d
release_migration_min=001
release_migration_max=044
release_verify=ok
expanded_secret_scan=ok
```

The expanded gate passes `15/15` portable release tests, the complete web and
contract suite passes `126/126`, and TypeScript passes. The two scan preview
trees totalled 122 MiB and were moved to the user's Trash. This build/verify
proof followed the schema-44 runtime smoke; the final authorized candidate
must still repeat the complete smoke after freeze.

## Current gates

- backend: `272 passed`;
- web/contracts: `126 passed`;
- portable release contracts: `15 passed`;
- worker launcher: `19 passed`;
- TypeScript typecheck: passed;
- shell syntax and scoped whitespace checks: passed;
- packaged production smoke: schema-44 preview passed with the real worker
  launcher and exact backend/frontend/worker release identity; the expanded
  scanner passes a subsequent clean archive build and verify.

A real immutable candidate still requires a clean authorized commit, remote
green CI, canary evidence and explicit owner GO.

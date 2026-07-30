# Local database backup and restore rehearsal — 2026-07-30

Scope: the canonical local Kolibri V3 development database only. Production,
Home and Primary were not changed. No database copy or credential was added to
the repository.

## Canonical runtime preflight

The same fail-closed preflight used by `scripts/dev-backend.sh` completed
against the exact V3 database:

```text
Kolibri V3 preflight: schema=43 users=7 platform_owner=1
```

This proves that the configured database reached the latest migration and
contains exactly one active platform owner with the required development
capabilities. It does not print or modify the owner's credential.

## Backup and restore result

`deploy/portable/database-rehearsal.py rehearse` ran against
`var/kolibri-v3.db` with an isolated mode-`0700` work directory:

```text
database_rehearsal=ok
database_schema_version=43
database_table_count=80
database_snapshot_sha256=193d004b80e6f4f47bdfe912fde430ca3b938338acfc8d2e4913d8303a9d5da4
database_write_probe=rolled_back
```

The helper:

- created the snapshot with SQLite's online backup API while leaving the
  source database open read-only;
- verified `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, schema 43 and
  80 application tables;
- atomically restored a byte-identical copy and required mode `0600` for both
  artifacts;
- performed a real `BEGIN IMMEDIATE` create/insert/read probe and rolled it
  back, then proved that the probe table did not remain;
- rejected a non-canonical work-directory alias and database symlink inputs.

The temporary backup and restored database were each 32,034,816 bytes. Their
SHA-256 values were identical. Both were explicitly removed after verification.

## Portable release preview

An isolated clean Git repository was assembled from the current, non-ignored
V3 source files. This synthetic commit is evidence for the working-tree
candidate only; it is **not** the immutable production RC and was not pushed:

```text
preview_commit=b377b4f1ecbd0600fed75f06ce8a110ac5915a2e
preview_files=759
release_id=kolibri-v3-b377b4f1ecbd-1a7b1b462f2c
release_sha256=b76defe08989977f540001578865362f0b0757d7f503cfa7377189a8010aee50
release_content_digest=1a7b1b462f2c562cb431787065453e4711574044feb1b04481484b44cda1e3a3
release_migration_min=001
release_migration_max=043
smoke_status=ok
```

The smoke gate verified the archive, manifest, checksum and provenance, then
used a fresh temporary database to run:

- web typecheck;
- all 117 web/contract tests;
- the optimized Next.js production build;
- migration and startup of the packaged backend and frontend;
- independent backend and frontend health checks.

The preview archive and its temporary repository were removed after evidence
was recorded. A real immutable RC still requires an authorized clean commit in
the primary repository, remote CI, canary and owner GO.

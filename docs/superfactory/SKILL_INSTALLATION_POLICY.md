# Skill Installation Policy

Status: active
Generated: 2026-07-02

## Principle

Skills are installed only through approved channels. No manual skill placement
on servers. Every installation is tracked, versioned, and rollback-capable.

## Installation Scope

| Scope | Nodes | Approval Required |
| --- | --- | --- |
| `dev` | Mac thin client | Skill Librarian |
| `server` | Any healthy server | Skill Librarian + Owner |
| `all_agents` | All agent nodes | Owner |

## Installation Process

1. Skill is registered in `09_SKILL_REGISTRY.md` with approved state.
2. Skill Librarian creates deployment manifest with version and checksum.
3. Control Plane dispatches sync task to target nodes.
4. Agent Host installs skill in isolated directory.
5. Skill is activated only after smoke test passes.
6. Installation is recorded in the skill sync ledger.

## Version Management

- Each skill has a semantic version (major.minor.patch).
- Breaking changes require major version bump.
- Rollback to previous version on regression.
- Version history is maintained in the skill manifest.

## Sync Rules

1. Only `approved_server` or `approved_all_agents` skills are synced to servers.
2. Skills are synced only to nodes matching their deployment scope.
3. Sync is idempotent: reinstalling the same version is a no-op.
4. Failed sync does not affect running skills.
5. Sync status is reported to Control Plane.

## Rollback

1. Skill regression detected by monitoring or owner report.
2. Skill Librarian triggers rollback to previous version.
3. Previous version is restored from artifact cache.
4. Root cause analysis is performed before re-promotion.

## Server Skill Sync Report

When sync is complete, a status report is generated:

- `docs/superfactory/SERVER_SKILL_SYNC_REPORT.md`
- `docs/superfactory/SERVER_SKILL_STATUS.md`
- `docs/superfactory/SKILL_ROLLOUT_MATRIX.md`

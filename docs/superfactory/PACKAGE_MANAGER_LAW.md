# Kolibri Package Manager Law

Date: 2026-07-03

This is the canonical package-change law for Kolibri Factory remote agents,
Control Plane tasks, Agent Host runners, service bootstraps, and fleet rollout.

## Default Rule

All package manager activity is default denied unless it is declared in a
Control Plane task envelope under `package_changes` or `package_policy.changes`
and passes the Agent Host package-policy gate.

Covered activity:

- `apt`, `dpkg`, service bootstrap packages, and OS package repositories
- `npm`, `npx`, `pnpm`, and `yarn`
- `pip`, `pipx`, and `uv`
- `go install`, `go get`, and module/tool installation
- `cargo install` and Rust toolchain package installation
- binary downloads, unpacked release artifacts, and installer scripts
- service/global installs and any mutation of node system state

## Required Manifest

Every package change entry must include these fields:

- `ecosystem`: one of `apt`, `dpkg`, `npm`, `npx`, `pnpm`, `yarn`, `pip`,
  `pipx`, `uv`, `go`, `cargo`, `binary`, or `service_bootstrap`
- `package`: package name or approved package spec
- `version`: exact version or bounded range; `latest`, `*`, and unbounded
  service/global installs are denied
- `source_registry`: source registry, repository, mirror, or release feed
- `purpose`: task-specific reason for the package
- `target_nodes`: explicit node list or rollout target pool
- `install_scope`: `ephemeral_task_env`, `node_service`, or `global`
- `canary`: canary node or canary procedure
- `rollback`: exact rollback/removal procedure
- `verification_commands`: commands proving install and expected behavior
- `provenance_security_license`: provenance, security, and license check
- `owner_approval_tier`: `none`, `reviewer`, `owner`, `owner_p0`, or `security`
- `cleanup_drift_plan`: cleanup, drift detection, and repair plan

## Default Deny

The following are denied unless explicitly quarantined and approved by
`owner_p0` or `security` where noted:

- `curl | bash`, `wget | sh`, and equivalent pipe-to-shell installers
- inline credential URLs in package specs or registries
- `git+`, `file:`, and `http://` package specs
- plain HTTP registries
- unpinned global or service installs
- package installs on Mac by remote agents
- unmanaged node mutation
- commands or flags that print secrets, tokens, env files, or raw credentials

Quarantine approval does not bypass secret handling, canary, rollback,
verification, managed marker, or drift requirements.

## Service, Global, And System Installs

Any `node_service` or `global` install must declare:

- canary first
- `batch_size` from 1 through 5
- rollback
- managed marker, such as a file under `/etc/kolibri/managed/`
- drift/repair policy
- owner approval appropriate to blast radius

`apt`, `dpkg`, `binary`, and `service_bootstrap` package changes cannot use
`ephemeral_task_env`; they are node mutations and must follow service/global
rollout controls.

## Ephemeral Test Packages

Ephemeral test dependencies must stay isolated in a task-local virtual
environment, `node_modules`, package cache, or artifact directory. They must not
mutate node system state, write to global package stores, alter service units,
or leave packages for future tasks to discover.

Allowed examples include task-local Python venv dependencies or task-local npm
dependencies used only for verification, provided the package change manifest
names cleanup and drift behavior.

## MIMO Code Rollout Rule

`@mimo-ai/cli` is allowed only as an npm registry package declared through this
law. It must not be installed from curl scripts, git URLs, local files, binary
drops, or inline credential URLs.

MIMO service rollout additionally requires:

- loopback-only bind host: `127.0.0.1`, `::1`, or `localhost`
- environment file path: `/etc/kolibri/mimocode.env`
- environment file mode: `0600`
- no raw secret output in logs, result JSON, verification, or owner reports
- canary first, batch size no larger than 5, rollback, managed marker, and
  drift/repair policy

## First Enforceable Gates

The first gate is implemented in `ops/agent_host.py`:

- task dispatch validates `package_changes`/`package_policy` before runner
  execution
- result finalization records `package_policy` and
  `package_policy_violations`
- violations block completion with `error_type: package_policy_violation`
- MIMO-specific service constraints are enforced in the manifest contract

Runtime command interception for arbitrary shell commands is a separate follow-up
because it touches every runner command path and must avoid breaking isolated
test environments. The exact follow-up envelope is recorded in this run's
`NEXT.md`.

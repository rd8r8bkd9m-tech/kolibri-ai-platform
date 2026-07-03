# Bug Sweep Fixes

## Alias Target Matching

- Issue: aliases such as `home-live` and `mesh-home` could produce different answers.
- Root cause: routing compared raw node IDs.
- Files changed: `ops/factory_registry.py`, `ops/factory_control.py`, tests.
- Test added: canonical alias matching without `mesh-agent-*` drift.
- Risk: low.
- Rollback: revert branch.
- Result: aliases are matched through registry.

## Capability Alias Matching

- Issue: `devops` and `github_review` aliases were not enforced by one shared contract.
- Root cause: capability matching was exact string matching.
- Files changed: `ops/factory_registry.py`, `ops/factory_control.py`, tests.
- Test added: devops and review aliases.
- Risk: low.
- Rollback: revert branch.
- Result: aliases are explicit and bounded.

## Queue Diagnostics

- Issue: queue could be blocked without a structured reason endpoint.
- Root cause: no diagnostics API in baseline branch.
- Files changed: `ops/factory_control.py`, tests.
- Test added: unleaseable task diagnostics.
- Risk: medium; read-only endpoint, no queue mutation.
- Rollback: revert branch.
- Result: diagnostics explain leaseable/blocked status.

## Bounded Task Listing

- Issue: full task listing can be huge and slow.
- Root cause: `/v1/tasks` returned all tasks unless caller filtered by state.
- Files changed: `ops/factory_control.py`.
- Test added: covered by existing task contracts and py_compile.
- Risk: low; old no-query behavior preserved.
- Rollback: revert branch.
- Result: summary/compact callers can request bounded output.


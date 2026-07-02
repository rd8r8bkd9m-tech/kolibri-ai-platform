# Control Plane Deploy Integrity And Namespace Packaging

Date: 2026-07-02

Scope: repository contracts, tests, and read-only ops scripts only. This package
does not deploy, restart, drain, cancel, merge, or mutate live Control Plane
runtime state.

## Live Facts Packaged

1. `P0_PR141_STAGE50_TIMEOUT_ROOT_CAUSE_NO_CODE_2026_07_02` proved the strict
   canary measured stale `/opt` runtime instead of the PR #141 head. Strict
   canaries must now pass a deployed-file SHA integrity gate before they run.
2. `P0_CONTROL_PLANE_QUEUE_REGISTRY_HYGIENE_AND_NAMESPACE_DRIFT_2026_07_02`
   cleaned synthetic canaries and patched one live Control Plane instance,
   `10.99.0.10`, with:
   - `GET /v1/filesystem`
   - `GET /v1/fleet/registry/hygiene`
   - `GET /v1/tasks?state=running&limit=...&cursor=...`

   The sibling instance `10.99.0.2` still returned 404 or empty running state
   during that observation window, so fleet namespace drift must remain visible
   until both instances report the same contracts.

## New Repo Contracts

- `GET /v1/filesystem` returns SHA-256, size, and existence metadata for
  Control Plane repo files. It rejects paths outside the repo root.
- `GET /v1/fleet/registry/hygiene` reports synthetic registry records,
  duplicate node IDs, missing node IDs, and namespace drift without deleting
  anything.
- `GET /v1/tasks` now pre-filters by `state` before applying `limit` and
  `cursor`, so strict state probes do not page over unrelated task states.
- `scripts/preflight-factory-control-runtime.sh` requires the new endpoints in
  the runtime contract before a deployment can be considered canary-ready.

## Strict Canary Gate

Use this gate before any strict canary command:

```bash
CONTROL_PLANE_URL=http://10.99.0.10:9101 \
  scripts/strict-canary-with-integrity-gate.sh -- pytest -q tests/test_factory_runtime_contracts.py
```

For SHA verification only:

```bash
python3 scripts/verify-control-plane-deployed-sha.py \
  --control-plane-url http://10.99.0.10:9101 \
  --repo-root .
```

If any deployed SHA differs from the local GitHub checkout, the gate exits
non-zero and the strict canary must not run. The next action is a separate,
owner-approved deployment or runtime repair task.

## Verification

Focused local verification:

```bash
python3 -m pytest -q tests/test_factory_runtime_contracts.py tests/test_factory_control_runtime_import_path.py
```

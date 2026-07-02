# Next

Next exact task:

`P0_REPAIR_PARIS_HIGHLOAD_AGENT_HOST_CONNECTIVITY_2026_07_02`

## Objective

Restore or definitively classify `hostvds-paris-highload` connectivity and live Agent Host telemetry.

## Required Scope

- Target: `hostvds-paris-highload` / `paris` / `mesh-paris`
- Mode: infrastructure diagnostic and repair only
- Allowed changes: SSH/Agent Host reachability repair, Control Plane heartbeat restoration, read-only resource probes, artifact updates
- Forbidden changes: product code changes, secret printing, force push, push to main, destructive git commands, production deploys unrelated to Agent Host reachability

## Required Verification

1. Prove one of:
   - SSH reaches `hostvds-paris-highload` from an approved server-side route, or
   - SSH is intentionally closed and Agent Host/API has another approved management path.
2. Restore fresh Control Plane card for Paris with:
   - heartbeat under 120 seconds old
   - CPU count
   - available RAM
   - root disk free/used
   - runner capabilities, if any
3. Run bounded readiness checks:
   - API health route
   - disk/inode budget
   - CPU/load budget
   - toolchain presence for build workloads
   - model workload capacity classification
4. Produce Russian owner-facing result with explicit `ready`, `limited`, or `blocked` status.


# Plan

Task: `P0_AUTOPILOT_EXTRA_30_HOSTVDS_AGENT_08_READINESS_REMOTE_PROBE_2026_07_02`

1. Submit a child Control Plane task constrained to `mesh-agent-08`.
2. Verify the lease owner is `mesh-agent-08:agent-host-mesh-agent-08`.
3. Collect only sanitized readiness evidence: node identity, API route, GitHub CLI auth status, disk, runner status, blockers, artifacts and next task.
4. Relay the useful remote result into canonical dispatcher artifacts without modifying product code.


# Plan

Task: `P0_PRIMARY_CANDIDATE_CONTROL_PLANE_LEASE_STORM_PERMANENT_REPAIR_2026_07_02`

1. Reuse the server-authored implementation from `primary-candidate` commit `4619252`, relayed as this branch commit.
2. Keep `/v1/tasks/lease` on a bounded fast path and prevent per-request global lease reaper scans.
3. Add singleflight lease reaper gating, bounded queue scans, Redis socket reuse, and Agent Host backoff/jitter.
4. Keep health and task listing cheap under lease pressure.
5. Validate with targeted runtime tests and a 1000 logical poll simulation.
6. Defer runtime deployment and PR #119 canary until a separate staged canary task.

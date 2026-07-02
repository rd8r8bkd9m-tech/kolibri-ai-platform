# Plan

Task: P0_CONTROL_PLANE_1000_AGENT_CAPACITY_REPAIR_2026_07_02

1. Bound Control Plane resource usage under 1000+ logical lease pollers.
2. Remove per-command Redis socket churn while preserving the stdlib RESP client.
3. Stop lease reaper scans from running on every lease request.
4. Add Agent Host jitter/backoff so idle hosts do not poll in lockstep.
5. Prove the behavior with in-process 1000 logical poll simulation and existing runtime contract tests.


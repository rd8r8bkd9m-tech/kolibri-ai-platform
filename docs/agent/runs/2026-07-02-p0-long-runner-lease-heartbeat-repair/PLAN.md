# PLAN

Task: P0_AGENT_HOST_LONG_RUNNER_LEASE_HEARTBEAT_REPAIR_AND_MIMO_REQUEUE_2026_07_02

1. Inspect existing Agent Host, Factory Control Plane, dispatcher, tests, CI, and prior direct-server artifacts.
2. Add shared long-running heartbeat coverage for runner paths that can block longer than `FACTORY_LEASE_DURATION`.
3. Ensure heartbeat failures become structured task failures with artifacts.
4. Make control-plane reaping and status output lease/heartbeat aware.
5. Add fake-runner tests for long-running success, heartbeat failure, direct MIMO, Codex-like, FormulaLM-like/API runner, and status visibility.
6. Document the lease contract and safe requeue plan.
7. Run requested tests and record exact results.

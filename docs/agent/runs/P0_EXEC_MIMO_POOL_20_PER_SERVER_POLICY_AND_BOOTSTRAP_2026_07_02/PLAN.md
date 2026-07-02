# Plan

Task: `P0_EXEC_MIMO_POOL_20_PER_SERVER_POLICY_AND_BOOTSTRAP_2026_07_02`

Goal: make the 20-MIMO-agents-per-server rule enforceable through shared policy, Agent Host bootstrap/heartbeat payloads, service templates, command helpers and owner-visible status.

Steps:

1. Add a shared MIMO pool policy contract with a default cap of 20 agents per server, resource caps and external API guardrails.
2. Enforce the cap in Agent Host runtime by clamping `max_inflight` and reporting pool state on register, heartbeat and lease.
3. Expose the pool policy through Control Plane node classification, Fabric policy and bootstrap metadata.
4. Surface per-node and aggregate MIMO capacity in backend factory status.
5. Add reversible systemd/service helper artifacts for slot-based start/stop/status without changing live services.
6. Verify with focused tests and preflight.

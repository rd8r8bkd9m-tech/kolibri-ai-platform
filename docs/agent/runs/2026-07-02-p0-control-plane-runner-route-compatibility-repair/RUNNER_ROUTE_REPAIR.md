# Runner Route Repair

Problem observed:

- `P0_PR119_PR125_RUNTIME_STACK_OWNER_REVIEW_AND_CANARY_GATE_2026_07_02`
  failed after three attempts with `/usr/bin/codex exec` runtime errors.
- `P0_API_FIRST_SUPERFACTORY_FABRIC_PRODUCTION_GAP_AND_CANARY_2026_07_02`
  failed after three attempts with codex unavailable.
- `P1_MIMO_API_AGENT_ROUTING_UNIFIED_CONTRACT_2026_07_02` failed after three
  attempts with `/usr/bin/codex exec` runtime errors.

Repair:

- Make Control Plane determine `effective_task_runner`.
- Require runner capability before lease.
- Default implicit `owner_remote_task` to MIMO runner, matching Agent Host.
- Keep MIMO Pool bootstrap pinned to `target_node=mesh-agent-20`.

Expected effect after deploy:

- A node without `runner:codex` cannot lease `runner=codex` work.
- A node without `runner:mimo` cannot lease implicit/default MIMO work.
- A non-target node cannot lease the selected MIMO Pool bootstrap task.


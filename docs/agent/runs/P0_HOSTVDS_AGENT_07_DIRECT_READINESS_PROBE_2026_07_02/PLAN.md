# P0 hostvds-agent-07 / mesh-agent-07 direct readiness probe

Task id: `P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02`

Date: `2026-07-02`

Scope:
- Run a read-only readiness probe from the checked-out worktree on the leased node.
- Do not modify product code.
- Do not push.
- Do not print secrets, raw auth output, environment files, tokens, cookies, private keys or credential helper output.
- Record only owner-safe readiness facts and exact next repair task.

Required facts:
- node identity;
- agent name;
- current task / runner availability;
- disk free / total for `/`;
- GitHub auth classification as `ok`, `missing` or `blocked_unknown`;
- locally observable API route / Control Plane reachability;
- blockers;
- artifact paths;
- next exact repair task.


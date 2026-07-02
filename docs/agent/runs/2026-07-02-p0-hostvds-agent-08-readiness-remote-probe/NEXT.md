# Next

Next exact task:

`P0_REPAIR_HOSTVDS_AGENT_08_CONTROL_PLANE_ROUTE_AND_GH_CLI_READINESS_2026_07_02`

Scope:

- On `hostvds-agent-08 / mesh-agent-08`, inspect why `kolibri-factory-control` is active but not reachable on expected `127.0.0.1:9101`.
- Verify service bind address, port, and sanitized logs without printing env or secrets.
- Install or expose GitHub CLI only if approved by node policy, then rerun `gh auth status` with redaction.
- Restore/start persistent Agent Host only under explicit service-repair authorization.
- Add a safe MIMO auth-status wrapper or approved non-secret probe.
- Rerun the same readiness probe and require exact `PLAN/ACTIONS/TESTS/RESULT/NEXT/READINESS_MATRIX/REMOTE_RESULT` artifacts.


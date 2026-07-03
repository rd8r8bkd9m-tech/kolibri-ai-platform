# Actions

- Confirmed this retry needs a repository delta, not only an external runner
  result.
- Read Kolibri GoMesh/Home gateway guidance and its architecture reference.
- Inspected existing run artifact and dispatcher envelope patterns, including
  `owner_remote_task`, `preferred_nodes`, `allowed_nodes`, exact output files,
  and Fabric fallback route shape.
- Located the rejected source attempt artifact:
  `/var/lib/kolibri-agent/artifacts/P0_HOME_KIOSK_ROUTE_ESCALATION_20260703_1839/P0_HOME_KIOSK_ROUTE_ESCALATION_20260703_1839-attempt-1/result.json`.
- Preserved the source attempt's useful classification: no Mac-local
  implementation, no dispatch submission, no live service mutation, and no
  secret material.
- Created the exact required run artifacts:
  `PLAN.md`, `ACTIONS.md`, `RESULT.md`, `NEXT.md`, and `ROLLBACK.md`.
- Added a dispatchable next envelope at
  `docs/agent/dispatcher/envelopes/P0_HOME_KIOSK_REPAIR_REMOTE_2026_07_03.json`.
- Kept this task docs/envelope-only. No Home kiosk command, browser command,
  tmux mutation, MikroTik command, GoMesh dataplane command, service restart,
  credential read, or production route change was executed.

Prepared route:

1. Resolve Home through Fabric API:
   `POST /v1/fabric/route` with `target_node=home`.
2. Submit the Home-bound task through Control Plane:
   `POST /v1/tasks` using the envelope
   `P0_HOME_KIOSK_REPAIR_REMOTE_2026_07_03.json`.
3. If Home direct routing is unavailable, use
   `primary-candidate` only for `/v1/fabric/relay` forwarding or blocked-route
   classification.
4. If the relay cannot reach Home, return the blocked response shape from the
   envelope and do not implement the kiosk on the relay node.

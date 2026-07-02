# Next

Next exact task:

`P0_FLEET_30MIN_FRESHNESS_REPAIR_AND_THIRD_WAVE_RELEASE_GATE_2026_07_02`

Goal:

Repair or quarantine stale fleet node cards, then rerun a third 30-minute
primary-candidate release gate wave.

Required work:

- Make `/v1/fleet/nodes` expose truthful freshness per node, or suppress stale
  `online` claims from the release capacity signal.
- Reconcile or drain nodes with heartbeat age greater than 30 minutes.
- Keep Telegram Gateway single-receiver verification owner-gated and
  no-mutation unless explicit approval is granted.
- Install or provide the missing verifier environments for broad Python and
  frontend build checks, or record them as node packaging blockers.
- Rerun the same route, service, focused test, and freshness matrix.

Exit requirement for the third wave:

- Factory Control primary routes return HTTP 200.
- Focused runtime tests pass.
- No new service/runtime blockers appear.
- Fleet freshness meets the 30-minute P0 exit threshold.
- Telegram receiver ownership is proven or explicitly scoped out by owner
  decision.

# Next

Next action:

`P0_DEPLOY_FACTORY_ROUTE_FRESHNESS_GATE_CANARY_2026_07_02`

Scope:

- Deploy the checked-in route freshness guard after preflight.
- Restart only `kolibri-factory-control.service` if owner/control-plane policy
  authorizes deployment.
- Re-probe `/v1/nodes`, `/v1/fleet/route?target_node=primary-candidate`, and
  `/v1/fleet/route?target_node=primary-candidate&required_capability=generic_implementation`.
- Expected post-deploy behavior: a stale or degraded heartbeat-classified
  `primary-candidate` must not be returned as a direct route; fresh fallback
  nodes may be listed.

Restart/rollback status for this task:

- Restart performed: `false`.
- Rollback needed: `false`.
- Exact restart command intentionally not executed in this task.
- Blocker for live completion: deployment artifact and rollback approval are
  required before mutating the live Factory Control service.


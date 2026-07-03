# Result

Status: implemented and locally verified.

`/v1/nodes` now reconciles active task heartbeat into node card health when all of these are true:

- task state is `leased`, `running`, or `review`;
- task heartbeat age is within `FACTORY_NODE_STALE_AFTER`;
- task lease has not expired;
- task `lease_owner` maps to the node id.

For a stale node heartbeat with a fresh active task heartbeat, the card is returned as effective `fresh` and `online`, with `status=running_with_stale_node_heartbeat`. The original node heartbeat state remains visible through `node_freshness`, `node_health`, and `node_heartbeat_age_seconds`.

Expired task leases do not upgrade the node card, so genuinely dead nodes remain stale.

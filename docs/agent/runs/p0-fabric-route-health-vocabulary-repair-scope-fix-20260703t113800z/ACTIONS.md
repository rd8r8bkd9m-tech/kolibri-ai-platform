# Actions

- Added explicit `ROUTABLE_NODE_HEALTH` vocabulary for Fabric routing.
- Updated route eligibility to reject draining nodes even when their reported health is otherwise routable.
- Added focused tests for `fresh`, `online`, `ok`, `running`, stale/degraded/offline/drained, and missing capability behavior.

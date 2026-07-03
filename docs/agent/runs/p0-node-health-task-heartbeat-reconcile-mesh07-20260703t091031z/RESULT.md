# Result

The node health reconciliation repair was preserved from commit `2e45105`.

`/v1/nodes` now reconciles node cards with fresh active task heartbeat only when the task state is active, the heartbeat is within `FACTORY_NODE_STALE_AFTER`, and the lease is not expired. Expired or terminal work does not mask a stale or dead node heartbeat.

Original node heartbeat evidence remains available on reconciled cards so NOC can show the worker as active while still exposing the stale node-heartbeat condition.


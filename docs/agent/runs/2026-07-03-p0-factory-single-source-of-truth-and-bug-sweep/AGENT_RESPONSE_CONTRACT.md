# Agent Response Contract

Every technical answer must include:

- source checked;
- timestamp;
- node, service or task ID;
- status;
- evidence;
- fallback;
- next action.

## Server Count Answer

Separate these numbers:

- canonical physical servers;
- logical worker nodes;
- Control Plane record total;
- online;
- fresh;
- degraded;
- stale;
- unknown.

## Server Unavailable Answer

```json
{
  "status": "blocked|degraded|rerouted",
  "node": "...",
  "reason": "...",
  "evidence": "...",
  "fallback_nodes": [],
  "can_continue_elsewhere": false,
  "repair_task": "..."
}
```


# Reporting Policy

Default reports: 10:00 and 18:00 MSK, plus failed task, stale heartbeat, deploy
blocker, or incident.

Report format:

```text
FACTORY STATUS
- queued:
- running:
- review:
- blocked:
- completed:
- failed:

ACTIVE AGENTS
- server:
- role:
- task:
- progress:
- heartbeat:

QUALITY
- tests:
- reviews:
- incidents:

RESOURCES
- servers available:
- CPU/GPU utilization:
- current estimated cost:

DECISIONS
- ...

NEXT ACTIONS
- ...
```

Full logs stay in `.factory/logs/`. Reports include conclusions and artifact
paths only.

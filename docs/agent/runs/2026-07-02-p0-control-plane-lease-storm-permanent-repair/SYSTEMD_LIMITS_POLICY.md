# Systemd Limits Policy

Systemd limits are required defense-in-depth, not the permanent fix.

Current emergency mitigation on `primary-candidate`:

```ini
[Service]
LimitNOFILE=65536
TasksMax=4096
```

Permanent policy:

- Keep `LimitNOFILE` high enough for Control Plane, Redis sockets, and diagnostics.
- Keep `TasksMax` explicit so request-handler growth has an outer guard.
- Do not use higher limits as a substitute for bounded lease path behavior.
- Deploy worker-pool increases only through staged canary.
- Keep rollback script paths in canary artifacts.

Required runtime canary metrics:

- fd count
- thread count
- Redis connected clients
- lease 5xx count
- `/v1/health` p95
- `/v1/tasks?limit=100` p95
- Agent Host process count

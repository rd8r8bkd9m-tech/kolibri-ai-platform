# Next

Next exact task:

`P0_DEPLOY_FACTORY_SUPERVISOR_CANARY_2026_07_02`

Recommended live canary steps:

1. Pull this branch into a clean remote worktree.
2. Start with supervisor mutation disabled:

```bash
FACTORY_SUPERVISOR_ENABLED=0 python3 ops/factory_control.py --bind 127.0.0.1 --port 9101
curl -s http://127.0.0.1:9101/v1/factory/supervisor
```

3. If status is healthy, enable the service:

```bash
FACTORY_SUPERVISOR_ENABLED=1 systemctl restart kolibri-factory-control.service
curl -s http://127.0.0.1:9101/v1/factory/supervisor
```

4. Confirm:

- `owner_summary_ru` is present.
- repair dispatch cap is `<= floor(node_count * 0.5)`.
- no duplicate task IDs appear in the queue.
- no secrets appear in service logs.

Rollback command:

```bash
FACTORY_SUPERVISOR_ENABLED=0 systemctl restart kolibri-factory-control.service
```

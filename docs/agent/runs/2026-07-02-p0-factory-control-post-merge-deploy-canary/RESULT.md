# Result

Status: `passed`

Task id: `P0_FACTORY_CONTROL_POST_MERGE_DEPLOY_CANARY_2026_07_02`

Node: `kolibri`

Service state:

- `kolibri-factory-control.service`: `active/running`
- PID after restart: `3588876`
- Runtime entrypoint: `/usr/bin/python3 /opt/kolibri-ai-platform/ops/factory_control.py`
- Working directory: `/opt/kolibri-ai-platform`

Route matrix:

| Route | HTTP | Result |
| --- | ---: | --- |
| `/health` | 200 | pass |
| `/v1/health` | 200 | pass |
| `/v1/fabric/health` | 200 | pass |
| `/v1/fabric/routes` | 200 | pass |
| `/v1/fleet/nodes` | 200 | pass |
| `/v1/models` | 200 | pass |

Safety:

- Remote execution happened on server/control node `kolibri`.
- Preflight ran on actual target repo path `/opt/kolibri-ai-platform` before restart.
- Only `kolibri-factory-control.service` was restarted.
- Telegram gateway remained `inactive/dead`; no Telegram service or Bot API state was touched.
- No product code, tests, CI files, main branch, secrets, or Telegram state were modified in the checked-out repository.

Backup and rollback:

- Backup path:
  `/var/backups/kolibri-runtime/20260701T214949Z-P0_FACTORY_CONTROL_POST_MERGE_DEPLOY_CANARY_2026_07_02`
- Rollback state: `not_needed`
- Rollback command path is recorded in `POST_DEPLOY_CANARY.md`.

Blockers: none for this canary.

Next exact task:

`P0_FACTORY_CONTROL_TELEGRAM_GATEWAY_OWNER_APPROVED_NO_MUTATION_DIAGNOSTIC_2026_07_02`


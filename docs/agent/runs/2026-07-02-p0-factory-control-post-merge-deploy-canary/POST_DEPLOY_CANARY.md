# Post Deploy Canary

Status: `passed`

Node: `kolibri`

Target repo path: `/opt/kolibri-ai-platform`

Service: `kolibri-factory-control.service`

| Route | HTTP | Result |
| --- | ---: | --- |
| `/health` | 200 | pass |
| `/v1/health` | 200 | pass |
| `/v1/fabric/health` | 200 | pass |
| `/v1/fabric/routes` | 200 | pass |
| `/v1/fleet/nodes` | 200 | pass |
| `/v1/models` | 200 | pass |

Backup path:

`/var/backups/kolibri-runtime/20260701T214949Z-P0_FACTORY_CONTROL_POST_MERGE_DEPLOY_CANARY_2026_07_02`

Rollback path:

- Unit rollback: restore `kolibri-factory-control.service.before` to `/etc/systemd/system/kolibri-factory-control.service`.
- Legacy entrypoint rollback: restore `kolibri-factory-control.before` to `/usr/local/bin/kolibri-factory-control`.
- Target file rollback: restore `*.before` files under the matching relative paths in `/opt/kolibri-ai-platform`.
- Reload systemd and restart only `kolibri-factory-control.service`.

Rollback state: `not_needed`.


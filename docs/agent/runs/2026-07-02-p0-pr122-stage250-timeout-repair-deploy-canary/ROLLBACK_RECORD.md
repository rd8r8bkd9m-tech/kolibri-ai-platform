# Rollback Record

Rollback state: `not_needed`

Rollback was not executed because the stage-250 canary completed without task claims, 5xx responses, health failures, BrokenPipe loops, fd growth, or thread instability.

Runtime backup set:

`/var/backups/kolibri-runtime/20260704T050348Z-REBROADCAST_P0_PR122_STAGE250_TIMEOUT_REPAIR_DEPLOY_AND_CANARY_2026_07_02-narrow`

Backup contents:

- `kolibri-factory-control.before`
- `kolibri-factory-control.candidate`
- `kolibri-factory-control.service.before`
- `kolibri-factory-control.env.before`
- `SHA256SUMS`

Recorded hashes:

```text
3867d1aebee27f5d6d9c9defc276c8a9c4c3065025bdf36d95623dec17ec98a1  kolibri-factory-control.before
e5bc57a84ecdc2aa1792270baeeda5a9761397f93d299902c07f45c56917f677  kolibri-factory-control.candidate
1ec10b3fb7d86bea4eb716abf16bed44666b3090bc2d1f47e9c482649cb7d99e  kolibri-factory-control.env.before
61f23b6efa6473c962472dfccf477212c3630621c40eb31f6253ce4a8237e884  kolibri-factory-control.service.before
```

Current live runtime hash after canary:

```text
80b273f0fa8fbfe40320c1b4c70816d190bea6ab86755b5d8d0965a0a62a7e99  /usr/local/bin/kolibri-factory-control
61f23b6efa6473c962472dfccf477212c3630621c40eb31f6253ce4a8237e884  /etc/systemd/system/kolibri-factory-control.service
```

Important rollback note:

The current live runtime includes PR #125 lease fast-path changes plus later route/admin hardening added after the narrow candidate backup. A blind restore of `kolibri-factory-control.before` would roll back PR #125 and those later runtime additions. Use it only for an emergency regression rollback, then re-apply later safe route/admin changes separately if needed.

Emergency rollback command:

```bash
backup=/var/backups/kolibri-runtime/20260704T050348Z-REBROADCAST_P0_PR122_STAGE250_TIMEOUT_REPAIR_DEPLOY_AND_CANARY_2026_07_02-narrow
sudo install -m 0755 "$backup/kolibri-factory-control.before" /usr/local/bin/kolibri-factory-control
sudo install -m 0644 "$backup/kolibri-factory-control.service.before" /etc/systemd/system/kolibri-factory-control.service
sudo systemctl daemon-reload
sudo systemctl restart kolibri-factory-control.service
curl -fsS http://10.99.0.2:9101/health
curl -fsS http://10.99.0.2:9101/v1/fabric/health
```


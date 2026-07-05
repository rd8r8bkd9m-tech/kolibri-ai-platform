# Actions

- Confirmed node identity: `kolibri`, user `root`, Linux server kernel.
- Confirmed pre-canary Factory Control state: `active/running`, PID `3574728`.
- Created backup directory:
  `/var/backups/kolibri-runtime/20260701T214949Z-P0_FACTORY_CONTROL_POST_MERGE_DEPLOY_CANARY_2026_07_02`.
- Backed up:
  - `/etc/systemd/system/kolibri-factory-control.service`
  - `/usr/local/bin/kolibri-factory-control`
  - any existing target copies under `/opt/kolibri-ai-platform`.
- Staged only these runtime files into `/opt/kolibri-ai-platform`:
  - `ops/factory_control.py`
  - `ops/telegram_superfactory.py`
  - `ops/systemd/kolibri-factory-control.service`
  - `scripts/preflight-factory-control-runtime.sh`
- Ran preflight on `/opt/kolibri-ai-platform`; it returned `factory_control_runtime_preflight=ok`.
- Installed the Factory Control unit from the target repo path into `/etc/systemd/system/kolibri-factory-control.service`.
- Ran `systemctl daemon-reload`.
- Restarted only `kolibri-factory-control.service`.
- Did not start, restart, reload, reconfigure, or call Telegram.


# Actions

- Found runtime sender: `/usr/local/bin/kolibri-kfm-queue-steward`.
- Found systemd unit: `kolibri-kfm-queue-steward.service`.
- Found timer: `kolibri-kfm-queue-steward.timer`.
- Confirmed unit hard-coded `KOLIBRI_FACTORY_CONTROL_URL=http://10.99.0.2:9101`.
- Confirmed journal failures are timeouts while fetching `/v1/tasks`.
- Added repository-managed steward entrypoint: `ops/kfm_queue_steward.py`.
- Added fallback-aware unit templates under `ops/systemd/`.
- Added `tests/test_kfm_queue_steward.py`.
- Ran live smoke in `--diagnose-only` mode; no queue POST and no Telegram send.

No secrets, token values, chat ids, Redis cleanup, queue mutation, service restart, broad deploy, main push, or force push were performed.

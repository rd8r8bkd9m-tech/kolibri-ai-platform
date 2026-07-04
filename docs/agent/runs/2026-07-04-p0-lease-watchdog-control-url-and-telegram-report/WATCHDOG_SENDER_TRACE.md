# Watchdog Sender Trace

Script path:

- Runtime: `/usr/local/bin/kolibri-kfm-queue-steward`.
- Repository replacement: `ops/kfm_queue_steward.py`.

Systemd:

- Service: `kolibri-kfm-queue-steward.service`.
- Timer: `kolibri-kfm-queue-steward.timer`.
- Timer cadence: `OnBootSec=90s`, `OnUnitActiveSec=60s`, randomized delay `10s`.

Configured Control Plane URL:

- Runtime unit currently sets `KOLIBRI_FACTORY_CONTROL_URL=http://10.99.0.2:9101`.
- Replacement unit sets `KOLIBRI_FACTORY_CONTROL_URLS=http://10.99.0.1:9101,http://10.99.0.10:9101,http://10.99.0.2:9101`.

Telegram route:

- Replacement script only sends Telegram when `--notify` is passed and token/chat env vars are present.
- No token or chat id values were read or printed.

Artifact path:

- `/var/lib/kolibri-agent/kfm-steward/latest.json`.

Duplicate senders:

- Local systemd search found one `kolibri-kfm-queue-steward.service` and one timer on `server-kfrm`.
- No cron sender was found in `/etc/cron*`.

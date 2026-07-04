# Next

1. Review and merge PR after CI.
2. Copy/install `ops/kfm_queue_steward.py` as `/usr/local/bin/kolibri-kfm-queue-steward`.
3. Install updated `ops/systemd/kolibri-kfm-queue-steward.service`.
4. Run one owner-approved canary `systemctl start kolibri-kfm-queue-steward.service`.
5. Verify `/var/lib/kolibri-agent/kfm-steward/latest.json` and owner Telegram text.

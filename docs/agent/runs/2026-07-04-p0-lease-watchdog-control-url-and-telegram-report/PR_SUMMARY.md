# PR Summary

Title:

`P0: Repair Lease Watchdog Control Plane fallback and Telegram report`

Summary:

- Adds repository-managed KFM queue steward with fallback URL support.
- Adds owner-safe human Telegram message formatter.
- Adds systemd templates with `KOLIBRI_FACTORY_CONTROL_URLS`.
- Adds regression tests.
- Documents sender trace, URL diagnosis, fallback policy, samples and smoke result.

Blockers:

- Runtime `/usr/local/bin/kolibri-kfm-queue-steward` still needs owner-approved deploy/canary.
- No service restart was performed in this branch.

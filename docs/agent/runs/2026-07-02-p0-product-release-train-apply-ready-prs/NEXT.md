# Next

Owner action:

1. Review PRs #113, #109, #105, #110, #112, #106, #111, #108, and #107 in that order.
2. For any PR selected for merge, first recheck that its head SHA and Kolibri CI run still match `RELEASE_TRAIN_QUEUE.md`.
3. Only after explicit owner approval, mark the selected PR ready and merge through the protected queue.

Follow-up task:

- Run post-merge canaries after each runtime-affecting merge, especially Factory Control import path, factory status proxy, Fabric route freshness, primary heartbeat freshness, and runner contract changes.

# NEXT

1. Push branch `p0/pr137-http-worker-thread-growth-repair-2026-07-02` and open a draft PR stacked on PR #137.
2. Wait for GitHub CI.
3. If CI succeeds, deploy only `ops/factory_control.py` to primary-candidate runtime with backup.
4. Run strict runtime canary stages `20/50/100/250/500/1000`.
5. Strict pass requires all six stages, no `status0`, no 5xx, created/leased equality, and no canary fail reason.
6. If canary fails, rollback immediately and dispatch the next narrow repair.
7. PR #119 remains blocked until this strict runtime canary passes.

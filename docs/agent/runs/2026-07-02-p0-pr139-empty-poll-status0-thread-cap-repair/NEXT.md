# NEXT

1. Push this stacked repair branch to GitHub.
2. Open a draft PR based on `p0/pr137-http-worker-thread-growth-repair-2026-07-02`.
3. Wait for GitHub CI.
4. If CI is green, deploy only `ops/factory_control.py` to `primary-candidate` with a timestamped backup.
5. Run the strict runtime canary stages `20/50/100/250/500/1000`.
6. If any stage has lease/empty `status 0` or `5xx`, rollback immediately and dispatch the next repair.
7. If all stages pass, keep runtime live and rerun the PR #119 release gate.

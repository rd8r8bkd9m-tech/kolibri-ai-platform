# NEXT

1. Push this branch and open a draft PR stacked on PR #135.
2. Wait for GitHub CI.
3. If CI succeeds, perform a controlled runtime deploy of only `ops/factory_control.py` with backup.
4. Run strict runtime canary stages 20/50/100/250/500/1000.
5. If strict canary passes, unblock PR #119 release-gate rerun.
6. If strict canary fails, rollback runtime and dispatch the next focused repair.

PR #119 remains blocked until strict runtime canary is clean.

# NEXT

Recommended relay path:

1. Push branch `codex/pr140-empty-lease-latency-repair`.
2. Open a stacked PR targeting PR #140's branch, or retarget after PR #140 lands.
3. Run GitHub CI.
4. After owner approval, deploy to the canary runtime.
5. Rerun strict empty-poll canary stages including `250`, `500`, and `1000`.

Do not merge directly to `main` from this implementation branch.
Do not deploy runtime without the separate owner-approved deploy task.

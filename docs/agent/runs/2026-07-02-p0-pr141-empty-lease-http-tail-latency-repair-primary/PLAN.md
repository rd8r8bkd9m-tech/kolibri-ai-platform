# PLAN

- Continue from PR #141 requested head `656e07ef5323dd6a28a941e72eeb08d5b7c1adcc`; local refs identify this commit on `codex/pr140-empty-lease-latency-repair`.
- Keep scope to per-request HTTP tail latency for high-volume empty `/v1/tasks/lease` polls.
- Preserve existing lease response contract and warmed Redis-bypass behavior.
- Add regression coverage for compact/pre-encoded no-task responses and access-log suppression.
- Do not merge.
- Do not deploy runtime.

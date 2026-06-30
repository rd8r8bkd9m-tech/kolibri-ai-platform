# Next

Next recommended task:

`P0_MERGE_AGENT_HOST_RUNNER_CONTRACT_AND_RERUN_INTEGRATION_AUDIT`

Why:

The Superfactory cannot safely become more autonomous until task completion is
trustworthy. Agent Host runner hardening must land first, then the P0
integration contract audit should be rerun.

Next sequence:

1. Finish PR #83: Agent Host runner contract hardening.
2. Rerun P0 integration contract audit through Control Plane.
3. Create GitHub always-current policy.
4. Inventory the whole fleet.
5. Repair `uiap`/`qjns` disk and server GitHub auth.
6. Preserve dirty runtime diffs from `main` and `primary-candidate`.
7. Start Home visual monitor UI/UX as a separate PR.

Do not merge this Superfactory canvas with product code changes.

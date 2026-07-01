# Owner Merge Batch Proposal

No merge batch is approved by this file.

The remote steward should produce a final owner-facing proposal with:

- PR numbers.
- Exact head SHAs.
- CI/check evidence.
- Scope summary.
- Why each PR is safe to merge now or why it must wait.
- Required post-merge canary.
- Whether the PR should be marked ready, merged, split, repaired, superseded, or closed.

Suggested first batch for review if remote evidence agrees:

1. Docs-only batch: #88 and #92.
2. Runtime-contract batch: #96 and #97.
3. Fabric/API batch: #85.

Hold until further review:

- #89 until Telegram receiver/cutover risk is closed.
- #91 until Agent Host/MIMO runner ordering is confirmed.
- #83 until overlap/supersession with #96 is resolved.

# P0 App Verify Review Envelope

Envelope:

```bash
ops/envelopes/KOL-P0-APP-VERIFY-REVIEW-20260629.json
```

Purpose: start an unattended factory review for completed P0 task `KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629`, which is currently `waiting_review` with execution status `completed`.

Extracted source values:

- Source task: `KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629`
- Review branch: `agent/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629/app-verify`
- Review commit: `0e7dc0011063740375ce21153aa72abaca197c2b`
- Base ref: `origin/codex/factory-autonomy-pwa-billing`
- Related PR: `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/46`

Submit it through the dispatcher from the repository root:

```bash
ops/kolibri-dispatch submit --file ops/envelopes/KOL-P0-APP-VERIFY-REVIEW-20260629.json
```

The envelope uses `kind=generic_implementation`, `required_capability=generic_implementation`, and `permission_pack=implementation`. Its goal requires the runner to review the target branch, verify the remote branch still points to the extracted commit, run the listed test commands, and create a review report plus PR or PR-ready handoff.

Safety constraints:

- No merge to `main`.
- No production deploy.
- No Control Plane queue mutation.
- No task drain, requeue, or cancellation.
- No FormulaLM/LLM/model benchmarks on Mac.

Local validation:

```bash
python3 -m json.tool ops/envelopes/KOL-P0-APP-VERIFY-REVIEW-20260629.json >/dev/null
git fetch origin 'refs/heads/agent/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629/app-verify:refs/remotes/origin/agent/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629/app-verify'
test "$(git rev-parse origin/agent/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629/app-verify)" = "0e7dc0011063740375ce21153aa72abaca197c2b"
```

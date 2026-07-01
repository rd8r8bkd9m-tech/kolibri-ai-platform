# Tests

Verification commands run or planned for this artifact pass:

```bash
python3 -m json.tool docs/agent/dispatcher/envelopes/P0_GITHUB_RELEASE_STEWARD_GREEN_DRAFT_QUEUE_DRAIN_MIMO_FALLBACK_2026_07_01.json >/dev/null
git diff --check
test -f docs/agent/runs/2026-07-01-p0-github-release-steward-green-draft-queue-drain-mimo-fallback/RESULT.md
test -f docs/agent/runs/2026-07-01-p0-github-release-steward-green-draft-queue-drain-mimo-fallback/GREEN_DRAFT_PR_MATRIX.md
test -f docs/agent/runs/2026-07-01-p0-github-release-steward-green-draft-queue-drain-mimo-fallback/RELEASE_TRAIN_ORDER.md
test -f docs/agent/runs/2026-07-01-p0-github-release-steward-green-draft-queue-drain-mimo-fallback/OWNER_MERGE_BATCH_PROPOSAL.md
test -f docs/agent/runs/2026-07-01-p0-github-release-steward-green-draft-queue-drain-mimo-fallback/POST_MERGE_CANARY_PLAN.md
```

Read-only environment checks:

```bash
hostname
env | sort | rg -i 'mimo|mesh|node|agent|kolibri|task|runner'
```

Read-only GitHub live check attempted:

```bash
gh pr view 83 --repo rd8r8bkd9m-tech/kolibri-ai-platform --json number,title,isDraft,mergeable,headRefOid,statusCheckRollup,updatedAt
```

Result: `gh` is not installed in this MIMO worker, so live GitHub status was not rechecked from this run. The fallback envelope snapshot was used instead.

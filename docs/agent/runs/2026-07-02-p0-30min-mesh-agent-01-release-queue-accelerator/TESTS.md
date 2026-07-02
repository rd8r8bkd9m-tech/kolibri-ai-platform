# Tests

Commands:

```bash
python3 -m pytest tests/test_release_queue_accelerator.py -q
python3 ops/release_queue_accelerator.py --known-merged 83,85,88,89,91,92,95,96,97,98 --priority 83,85,89,91,92,96,97,98,100,101,102,103,104 --output docs/agent/runs/2026-07-02-p0-30min-mesh-agent-01-release-queue-accelerator/PR_REF_ACCELERATOR_MATRIX.md
git diff --check
```

Expected:

- Parser preserves `main` SHA and sorts pull refs numerically.
- Known merged refs are classified as `merged_or_superseded_ref_visible`.
- Priority unknown refs are classified as
  `priority_ref_visible_metadata_required`.
- Markdown generation includes counts and the release queue warning that pull
  refs alone do not prove open/draft/mergeability/check status.

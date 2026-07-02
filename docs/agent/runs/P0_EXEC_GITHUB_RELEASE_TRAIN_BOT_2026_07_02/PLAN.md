# Plan

Task id: `P0_EXEC_GITHUB_RELEASE_TRAIN_BOT_2026_07_02`

Goal: create a working GitHub release-train mechanism that classifies pull
requests, updates PR release-train checklists, opens repair tasks for failing
PRs, enforces main freshness, and never merges to `main` without owner approval.

Execution plan:

1. Inspect existing release-train and dispatcher artifacts.
2. Add a reusable `gh`-backed release train CLI in `ops/`.
3. Keep all merge authority outside the bot; make owner approval an explicit
   checklist and classification gate.
4. Add focused unit tests for classification, stale-main gating, repair task
   generation, PR body update idempotency, and GitHub check parsing.
5. Verify locally and record any live-runtime blocker without printing secrets.


# Next

Exact next task:

`P0_AUTHENTICATED_GITHUB_PR_QUEUE_RECHECK_2026_07_02`

Objective:

From an authenticated server Agent Host or owner-approved command host, recheck PR #84, #99, #100, #101, #102, #104, #88, #87, #65, #90, and #103 for state, draft flag, base freshness, mergeability, reviews, and CI/check conclusions. Do not merge, approve, mark ready, close, push to `main`, or force-push without owner approval.

Required acceptance:

- Exact node and auth path are reported without printing secrets.
- Current `origin/main` SHA is recorded.
- Each candidate has exact PR metadata and check state.
- #90 is verified in a dependency-satisfied backend test environment or remains blocked with exact evidence.
- Docs candidates #84/#99/#100 are either proposed to owner as a merge batch or rejected with exact blocker evidence.

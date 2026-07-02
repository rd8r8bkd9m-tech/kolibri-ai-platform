# Actions

- Added `ops/release_queue_accelerator.py`, a read-only helper that parses
  `git ls-remote` output and renders a deterministic PR ref matrix.
- Added unit coverage in `tests/test_release_queue_accelerator.py`.
- Generated `PR_REF_ACCELERATOR_MATRIX.md` from live `origin` refs.
- Classified already merged/superseded priority refs as non-blocking for P0:
  #83, #85, #88, #89, #91, #92, #95, #96, #97, and #98.
- Promoted the remaining P0 blocker shape from generic PR queue drain to exact
  follow-up lanes: runtime Telegram no-mutation diagnostic, GitHub metadata
  recheck from a node with authenticated metadata access, and backlog grooming
  for refs that are not priority release blockers.

Safety:

- No secrets were printed.
- No PR was marked ready, approved, merged, closed, force-pushed, or pushed to
  `main`.
- No service restart, deploy, Telegram Bot API mutation, or credential mutation
  was performed.

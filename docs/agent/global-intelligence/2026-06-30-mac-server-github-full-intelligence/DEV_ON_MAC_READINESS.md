# Development on Mac readiness

## Verdict

Mac is usable as a development and analysis workstation for this project, with caveats.

## Good on Mac

- branch and PR analysis.
- docs/intelligence generation.
- small backend/frontend edits.
- light unit tests.
- frontend build checks.
- GitHub CLI operations through `/opt/homebrew/bin/gh`.
- Control Plane dispatch and status collection.

## Avoid on Mac

- FormulaLM/GPU/inference benchmarks.
- heavy Docker builds unless disk is cleared first.
- full cluster validation.
- server-only integration tasks.
- credential or secret extraction.

## Constraints

- current Mac worktree is dirty with generated `docs/`.
- available disk is only about 22 GiB on current filesystem.
- direct SSH reaches only 2 of 20 nodes from Mac route.
- GitHub CLI is not in default PATH.

## Recommended Mac cleanup later

Only after this docs task is safely saved:

- decide whether to stage/commit or move intelligence artifacts.
- clean prunable worktrees with explicit approval.
- add `/opt/homebrew/bin` to PATH for future GitHub CLI usage.
- free disk before large builds.

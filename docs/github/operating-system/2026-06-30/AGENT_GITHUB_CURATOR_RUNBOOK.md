# Agent GitHub Curator Runbook

## Daily

- Check open PR count.
- Check failed CI.
- Check blocked P0 issues.
- Check stale PRs.
- Check PRs labeled or inferred `status:needs-split`.
- Check branches created by agents in the last 24 hours.
- Update daily status template.

## After Every Agent Task

- Link task_id to issue/PR.
- Link artifact path or GitHub artifact.
- Confirm tests or unavailable-tests explanation.
- Confirm branch/PR exists when code/docs changed.
- Add labels if available and approved.

## Weekly

- Stale branch review.
- Milestone review.
- Project board hygiene.
- Roadmap update.
- PR #46 split progress review.
- Fleet/GitHub auth blockers review.

## Before Merge

- Scope is focused.
- CI is green.
- Tests are explicit.
- Risk and rollback are documented.
- Required owner approval is present.
- No secrets touched or leaked.

## After Merge

- Close or update linked issue.
- Update docs/status/changelog where appropriate.
- Mark branch as archive candidate, but do not delete without approval.

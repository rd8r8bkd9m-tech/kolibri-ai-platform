# Repository Governance

## Source Of Truth

GitHub is the durable source of truth for:

- branches;
- PRs;
- issues;
- CI state;
- release notes;
- governance docs;
- project board state;
- agent task ledger links;
- owner-visible roadmap.

Control Plane remains the live execution nervous system. Every Control Plane task that changes code, infrastructure, docs or artifacts should be linked back to a GitHub issue, PR or status artifact.

## Governance Rules

- No direct push to `main`.
- No force push.
- No automatic merge.
- No branch deletion without classification, archive plan and owner approval.
- No PR is ready without tests or an explicit unavailable-tests explanation.
- No mixed PRs across unrelated subsystems.
- No secrets, tokens, cookies, private keys or env values in logs, docs, PRs or issues.
- Dirty runtime repos must be preserved and classified before becoming a merge source.

## Required GitHub Objects

- Labels: priority, type, area, status, risk and agent group.
- Milestones: P0 Stabilization, GitHub OS, Fabric API, Fleet Repair, PR #46 Split.
- Project board: `Kolibri Factory OS`.
- Templates: PR template, bug, feature, agent task and infra task.
- CODEOWNERS: owner-gated review for sensitive zones.
- Runbooks: daily and weekly GitHub Curator routines.

## Agent Responsibility

GitHub Curator is not a one-time PR writer. It is an ongoing role that keeps issues, PRs, CI, branches, artifacts, project board and roadmap current after every factory action.

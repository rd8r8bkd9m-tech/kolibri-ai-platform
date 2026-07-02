# Skill: Kolibri GitHub Curator

## Metadata

| Field | Value |
| --- | --- |
| skill_id | `kolibri-github-curator` |
| version | `0.1.0` |
| scope | `server` |
| owner | GitHub Curator |
| status | `registered` |

## Purpose

Manage GitHub repository state: PRs, branches, CI status, releases, and
merge readiness. Keep `main` current and PR queue healthy.

## Trigger

- PR queue has merge-ready items
- `main` branch is stale relative to reality
- CI status changes on open PRs
- Release train requires stewardship

## Inputs

- Repository state (branches, PRs, CI status)
- PR queue matrix
- Release train schedule
- Owner merge approval signals

## Outputs

- PR merge readiness report
- Stale branch cleanup recommendations
- Release train status update
- Next merge candidate with evidence

## Safety Constraints

- Never push directly to `main`
- Never force push
- Never merge without CI passing
- Never merge without owner approval for production code
- Preserve dirty runtime diffs

## Dependencies

- GitHub API access
- CI system status
- Control Plane task dispatch

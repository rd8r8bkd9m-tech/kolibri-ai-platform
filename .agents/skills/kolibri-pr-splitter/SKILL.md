# Skill: Kolibri PR Splitter

## Metadata

 | Field | Value |
| --- | --- |
| skill_id | `kolibri-pr-splitter` |
| version | `0.1.0` |
| scope | `server` |
| owner | GitHub Curator |
| status | `registered` |

## Purpose

Decompose large mixed PRs into focused, reviewable changes. Separate product,
documentation, and operations changes into independent PRs.

## Trigger

- PR exceeds size threshold (files changed or diff lines)
- PR mixes unrelated subsystem changes
- Reviewer requests PR split
- Release train blocked by oversized PR

## Inputs

- PR diff and file list
- Change classification (product/docs/ops/test)
- Repository subsystem boundaries
- Reviewer feedback

## Outputs

- Split plan with exact file groupings
- Dependency order for split PRs
- Recommended PR titles and descriptions
- Risk assessment for each split piece

## Safety Constraints

- Never split without understanding full change scope
- Preserve all original changes in split PRs
- Ensure each split PR is independently mergeable
- No functional changes during split (pure reorganization)

## Dependencies

- GitHub API for PR manipulation
- Repository structure knowledge
- CI system for per-PR validation

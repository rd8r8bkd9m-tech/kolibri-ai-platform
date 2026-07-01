# Kolibri GitHub OS: Executive Summary

Task: `P0_GITHUB_OPERATING_SYSTEM_FOR_KOLIBRI_FACTORY`
Branch: `p0/github-operating-system-2026-06-30`
Repository: `rd8r8bkd9m-tech/kolibri-ai-platform`

## Purpose

GitHub must become the operational center for Kolibri Factory: branches, PRs, issues, labels, milestones, CI, releases, docs, artifacts and agent task state. Control Plane remains the live nervous system, but GitHub is the durable source of truth and owner-visible ledger.

## Current State

- Repository is private and uses `main` as default branch.
- Current remote branch count from `git ls-remote`: 97.
- Current open PR count from `gh pr list`: 27.
- Current open issue count from `gh issue list`: 31.
- Existing labels are sparse and inconsistent: `P0`, `bug`, `docs`, `factory`, `runtime`, etc.
- No milestones were found.
- Existing GitHub Projects: `Kolibri AI Platform: фабрика ИИ и продукт на миллиарды` and an untitled project.
- Branch protection API is blocked for this private repository by plan/visibility limitation.
- PR #46 is the largest active risk: it mixes PWA, billing, FormulaLM, runner, backend, DevOps and docs.

## Immediate Governance Decision

This PR applies safe repository artifacts only:

- docs under `docs/github/operating-system/2026-06-30/`;
- PR template;
- issue templates;
- CODEOWNERS draft;
- SECURITY and CONTRIBUTING drafts.

It does not:

- merge PRs;
- close issues;
- delete branches;
- push to `main`;
- change branch protection;
- create/modify production workflows;
- modify product code.

## Top Problems

1. PR #46 is too large and must be split before merge.
2. Runner/verifier contract still allows useful work to become failed or missing artifacts.
3. GitHub labels are too weak for a factory-scale task ledger.
4. Milestones are absent.
5. Branch protection/ruleset cannot be inspected/applied through current API access.
6. Many historical agent/TG branches need classification before archive.
7. Open PRs target non-main base branches, making review order unclear.
8. Server GitHub auth remains an infrastructure blocker.
9. Dirty runtime repos on `main` and `primary-candidate` need preservation tasks.
10. Issue/PR templates were missing, so PR quality gates were not standardized.

## First Next Move

After this PR: create or confirm P0 issues, apply label taxonomy, and make PR #46 split tracking the highest-priority GitHub Curator action.

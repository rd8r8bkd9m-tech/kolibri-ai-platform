# Plan

Task: `KOLIBRI_SUPERFACTORY_CANVAS_MASTER_PLAN_2026_07_01`

Goal: capture the owner-approved Superfactory master canvas as a GitHub-tracked
documentation package without mixing it into product, runner, Home UI, billing,
FormulaLM, or server repair PRs.

## Scope

- Create a canonical Superfactory canvas.
- Encode the factory law and responsibility boundary.
- Record the known current state.
- Record the execution order.
- Record how Kolibri should be assembled through GitHub PR layers.
- Produce the required run artifacts: `PLAN.md`, `ACTIONS.md`, `TESTS.md`,
  `RESULT.md`, and `NEXT.md`.

## Out Of Scope

- No product code changes.
- No server mutation.
- No Control Plane task submission.
- No merge of PR #46.
- No Home UI implementation.
- No local LLM installation.
- No finance or phone/video automation.

## Branch Strategy

- Base: `origin/main`
- Branch: `codex/kolibri-superfactory-master-canvas-2026-07-01`
- PR type: draft docs-only PR

## Acceptance

- GitHub contains the Superfactory master canvas.
- The package states that GitHub is source of truth.
- The package states that Mac is thin client / command center.
- The package states that Home is visual monitor UI/UX.
- The package states that remote servers run heavy execution.
- The package includes the factory law: no destruction, spam, deception, fake
  success, secret leakage, or authority bypass.
- The package includes the full execution order.
- The package includes all five required run artifact files.

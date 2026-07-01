# Plan

Task ID: `P0_PR83_SCOPE_CLEANUP_REMOVE_SUPERFACTORY_OVERLAP_2026_07_01`

Node: `kolibri`

Agent display name: `Автономный инженер`

Branch: `p0/agent-host-runner-contract-hardening-2026-06-30`

PR: <https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/83>

Scope:

1. Remove the unrelated Superfactory documentation files from PR #83 only:
   - `docs/superfactory/00_README.md`
   - `docs/superfactory/20_ROADMAP.md`
   - `docs/superfactory/TASKS.md`
2. Preserve Agent Host runner contract hardening, tests, contract docs, and the publish-after-verification gate.
3. Run the focused runner contract test with `python3`.
4. Push the existing PR #83 branch and report the new head SHA.

Non-goals:

- Do not modify PR #85.
- Do not revert unrelated work.
- Do not print secrets.

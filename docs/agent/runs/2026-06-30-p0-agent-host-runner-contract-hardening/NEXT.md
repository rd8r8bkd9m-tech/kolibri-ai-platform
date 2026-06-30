# Next

Recommended next task:

`PROMPT 2 - P0_CREATE_KOLIBRI_SUPERFACTORY_DOCUMENTATION_PACKAGE`

Goal:

Create the full Kolibri Superfactory operating manual as a docs-only branch
after Prompt 1 is accepted.

Constraints:

- Use server Control Plane for server-only scans.
- Do not push from no-push/read-only tasks.
- Preserve all dirty runtime diffs into safe artifacts before cleanup.
- Keep PRs split: runner contract hardening must not mix with frontend,
  billing, FormulaLM, Telegram UX, or server credential work.

Suggested acceptance:

- Docs-only branch.
- Create the full `docs/superfactory/` package from Prompt 2.
- No product code changes.
- No server mutation.
- No FormulaLM, billing, frontend, Telegram, model, or fleet repair
  implementation.

After Prompt 2, the next ordered task is:

`PROMPT 3 - P0_GITHUB_ALWAYS_CURRENT_CONTRACT`

The P0 integration contract audit remains an important later task in the canvas
queue and should run after runner hardening has landed in the environment where
Control Plane agents execute.

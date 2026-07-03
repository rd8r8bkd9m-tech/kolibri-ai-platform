# P0 GitHub PR Matrix Markdown Relay Next Steps

Run: `P0_GITHUB_PR_MATRIX_MARKDOWN_RELAY_MESH15_20260703T093604Z`

## Immediate Follow-Up

- Preserve the three verified draft PRs:
  - PR #153: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/153
  - PR #154: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/154
  - PR #155: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/155
- Do not create another PR for these three heads unless the existing draft PRs are closed or superseded.

## Revenue/Free-VPS Blocker

The requested branch is missing:

`codex/p0_revenue_free_vps_artifact_relay_repair_20260703t084153z`

Required follow-up:

- Locate the worker output for the revenue/free-VPS docs task.
- Push the completed artifact relay branch under the exact requested branch name, or provide the exact existing remote branch name.
- Include nonempty exact run artifacts under `docs/agent/runs/`.
- Run `git diff --check` and available markdown/JSON validation.
- Open a draft PR to `main` only after a valid remote head exists.

## Guardrails For Follow-Up

- Do not merge.
- Do not push directly to `main`.
- Do not force push.
- Do not expose secrets.
- Do not fabricate a PR URL while the revenue/free-VPS head is missing.

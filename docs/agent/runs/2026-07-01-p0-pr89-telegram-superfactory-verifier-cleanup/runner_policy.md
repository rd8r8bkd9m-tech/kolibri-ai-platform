# Runner Policy

This canonical run artifact summarizes the runner verifier policy already
implemented in PR #89. It documents policy and diagnostics only; it does not
change Telegram runtime behavior and does not claim live deployment.

Default runner order remains:

`codex,mimo,api,local_llm`

The image runner remains `image`.

Runtime code paths covered by PR #89:

- `codex`
- `mimo`
- `api`
- `local_llm`
- `image`

Broken or missing authentication is reported by environment variable name only.
Secret values are not printed in diagnostics, test output, owner-facing replies,
or this run documentation.

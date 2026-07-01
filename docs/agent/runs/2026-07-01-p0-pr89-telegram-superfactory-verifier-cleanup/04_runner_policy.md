# Runner Policy

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

# Tests

This is a docs-only master canvas package.

Checks run:

```bash
git diff --check
```

Planned GitHub validation:

- Open a draft PR against `main`.
- Let GitHub Actions validate repository-level checks.

Not run:

- Full pytest suite: not required for docs-only canvas.
- Remote heavy tests: not required for docs-only canvas.
- Control Plane task: not required for docs-only canvas.

Rules preserved:

- No server mutation.
- No secrets printed.
- No product code changed.
- No push to `main`.
- No destructive git commands.

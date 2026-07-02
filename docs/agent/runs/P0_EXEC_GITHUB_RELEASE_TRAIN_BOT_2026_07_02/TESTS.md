# Tests

Commands run:

```bash
python3 -m pytest tests/test_github_release_train_bot.py -q
```

Result: `6 passed in 0.12s`

```bash
python3 -m py_compile ops/github_release_train_bot.py tests/test_github_release_train_bot.py
```

Result: passed.

```bash
git rev-parse origin/main && git ls-remote origin refs/heads/main
```

Result: both resolved to `f7ac32c70406432a52752ca45d87e35d9f1facd3`, so the
local `origin/main` was fresh at verification time.

```bash
python3 ops/github_release_train_bot.py --repo . --update-bodies
```

Result: structured blocker because `gh` is unavailable on this node:

```json
{
  "error": "required executable not found: gh",
  "status": "blocked"
}
```


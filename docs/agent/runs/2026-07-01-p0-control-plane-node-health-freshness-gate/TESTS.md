# Tests

Remote verification reported:

```bash
hostname && uname -a
python3 -m pytest -q tests/test_factory_runtime.py
python3 -m pytest -q tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_factory_runtime_queue_contracts.py
python3 -m compileall -q ops backend tests
npm --prefix frontend run test:mobile-layout
git diff --check
```

Remote results:

- `tests/test_factory_runtime.py`: `6 passed`.
- Focused factory runtime suite: `14 passed in 0.09s`.
- Backend stale-online functional check with in-process `httpx` stub: passed.
- `compileall`: passed.
- Mobile layout guard: passed.
- `git diff --check`: passed.

Blocked remote checks:

- Full focused pytest collection was blocked by missing `httpx` on the server node.
- Frontend production build was blocked by missing `vite`/`node_modules`.
- Draft PR creation was blocked because `gh` is not installed on the server node.

Mac relay-only checks:

- `git diff --cached --check`: passed.
- `python3 -m py_compile` on touched Python files/tests: passed.
- Staged diff secret-like scan: no matches.

GitHub PR #97:

- Head: `f542c5c7e828091c2bf762f5ce24a30953dc0906`.
- Changed files: 8.
- GitHub check `ci`: success.
- Mergeable: `true`.
- Mergeable state: `clean`.

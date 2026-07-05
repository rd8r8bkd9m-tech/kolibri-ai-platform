# Tests

Remote successful checks:

```bash
git diff --check origin/main...HEAD
python3 -m compileall -q backend ops scripts
python3 -m pytest -q tests/test_fabric_control.py tests/test_prompt3_fabric_api_surface.py
```

Results:

- `git diff --check origin/main...HEAD`: passed.
- `compileall`: passed.
- Focused Fabric tests: `11 passed`.

Remote blocked checks:

```bash
python3 -m pytest -q
npm run build
```

Blockers:

- Full pytest failed during collection because the server system Python lacks `pydantic` and `httpx`.
- Frontend build was blocked because the server has Node `18.19.1`; Vite requires Node `20.19+` or `22.12+`.

Command-node checks:

- GitHub API confirms PR #85 CI success on head `30b7e5dc35e2ac6d1590a96a7b9dbadbf9ca80c8`.
- GitHub API confirms PR #85 mergeable clean.
- `git grep` found no conflict markers in `README.md` or `docs/superfactory` on updated PR #85 head.

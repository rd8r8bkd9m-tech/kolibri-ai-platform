# Tests

Verification commands:

```bash
.venv/bin/python -m pytest tests/test_factory_status.py -q
```

Expected result:

```text
3 passed
```

Frontend build command:

```bash
cd frontend && npx -y -p node@20 -c 'npm run build'
```

Expected result:

```text
vite build completes successfully
```

Artifact presence command:

```bash
for f in PLAN.md ACTIONS.md TESTS.md RESULT.md NEXT.md; do test -s "/var/lib/kolibri-agent/logical-workers/mesh-agent-09/artifacts/P0_HOME_NOC_WORKTREE_SALVAGE_ARTIFACT_RELAY_MESH09_20260703T091408Z/P0_HOME_NOC_WORKTREE_SALVAGE_ARTIFACT_RELAY_MESH09_20260703T091408Z-attempt-1/$f"; done
```

Expected result:

```text
all five required files are non-empty
```

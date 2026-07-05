# Backend Verifier Env Scope Repair Tests

Task ID: `P0_AGENT_HOST_BACKEND_VERIFIER_ENV_SCOPE_REPAIR_2026_07_01`

Environment:

- Worktree: `/var/lib/kolibri-agent/worktrees/P0_AGENT_HOST_BACKEND_VERIFIER_ENV_SCOPE_REPAIR_2026_07_01/P0_AGENT_HOST_BACKEND_VERIFIER_ENV_SCOPE_REPAIR_2026_07_01-attempt-1/repo`
- Branch: `p0/agent-host-runner-contract-hardening-2026-06-30`
- Local head: `4b8d2a9f431034963945ffc929a7c19e3c7ff640`
- Remote head: `4b8d2a9f431034963945ffc929a7c19e3c7ff640`

Commands run:

```bash
git ls-remote origin refs/heads/p0/agent-host-runner-contract-hardening-2026-06-30
```

Result: passed,
`4b8d2a9f431034963945ffc929a7c19e3c7ff640 refs/heads/p0/agent-host-runner-contract-hardening-2026-06-30`.

```bash
find docs/agent/runs/2026-07-01-p0-agent-host-backend-verifier-env-contract -maxdepth 1 -type f -printf '%f\n' | sort
```

Result: passed, exact files:

```text
ACTIONS.md
NEXT.md
PLAN.md
RESULT.md
TESTS.md
```

```bash
python3 -m pytest tests/test_agent_host_runner_contract.py -q
```

Result: passed, `28 passed in 32.66s`.

```bash
find docs/agent/runs/2026-07-01-p0-agent-host-backend-verifier-env-scope-repair -maxdepth 1 -type f -printf '%f\n' | sort
```

Result: passed, exact files:

```text
ACTIONS.md
NEXT.md
PLAN.md
RESULT.md
TESTS.md
```

```bash
python3 - <<'PY'
from pathlib import Path
import subprocess
allowed_exact = {
    '.gitignore',
    'docs/agent/AGENT_RUNNER_CONTRACT.md',
    'ops/agent_host.py',
    'tests/test_agent_host_runner_contract.py',
}
allowed_dirs = (
    'docs/agent/runs/2026-07-01-p0-agent-host-backend-verifier-env-contract/',
    'docs/agent/runs/2026-07-01-p0-agent-host-backend-verifier-env-scope-repair/',
)
changed = subprocess.check_output(['git', 'diff', '--name-only', '23e8e43..HEAD'], text=True).splitlines()
changed += subprocess.check_output(['git', 'diff', '--name-only'], text=True).splitlines()
changed += subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], text=True).splitlines()
violations = sorted({p for p in changed if p not in allowed_exact and not any(p.startswith(d) for d in allowed_dirs)})
for run_dir in allowed_dirs:
    files = sorted(Path(run_dir).glob('*'))
    direct = [p.name for p in files if p.is_file()]
    if direct != ['ACTIONS.md', 'NEXT.md', 'PLAN.md', 'RESULT.md', 'TESTS.md']:
        violations.append(f'{run_dir} files={direct}')
if violations:
    print('violations:')
    print('\n'.join(violations))
    raise SystemExit(1)
print('scope audit passed')
print('changed files covered:', len(sorted(set(changed))))
PY
```

Result: passed, `scope audit passed`, `changed files covered: 14`.

Acceptance coverage:

- PR #83 branch is at the useful prior head `4b8d2a9`.
- Focused runner contract tests passed and include backend verifier environment
  contract coverage.
- Corrected scope accounts for `.gitignore`,
  `docs/agent/AGENT_RUNNER_CONTRACT.md`, `ops/agent_host.py`,
  `tests/test_agent_host_runner_contract.py`, and both exact run artifact
  directories from base `23e8e43`.

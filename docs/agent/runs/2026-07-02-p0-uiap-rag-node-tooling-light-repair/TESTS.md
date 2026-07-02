# Tests

Verification commands run:

```bash
hostnamectl 2>/dev/null || (hostname && uname -a)
df -h . /var/lib/kolibri-agent 2>/dev/null
git branch --show-current
git remote -v | sed -E 's#(https?://)[^/@]+@#\1***@#g; s#(ssh://)?git@([^/:]+)[:/].*#git@\2:***#g'
git status --short
command -v codex || true
command -v gh || true
command -v git || true
command -v python3 || true
command -v node || true
command -v npm || true
command -v redis-cli || true
git --version
python3 --version
node --version
npm --version
codex --version
gh --version 2>/dev/null | head -2 || true
systemctl show kolibri-agent-host.service -p LoadState -p ActiveState -p SubState -p UnitFileState -p FragmentPath -p MainPID -p User -p WorkingDirectory --no-pager
python3 -m compileall -q ops backend scripts
python3 -m pytest -q tests/test_agent_host_runner_contract.py tests/test_agent_host_permission_contract.py tests/test_factory_runtime_contracts.py
bash scripts/preflight-factory-control-runtime.sh .
git ls-remote --heads origin agent/P0_UIAP_RAG_NODE_TOOLING_LIGHT_REPAIR_2026_07_02/generic
git ls-remote --symref origin HEAD
```

Results:

- Host probe: passed; server host `kolibri`, Ubuntu 24.04 LTS, KVM, x86-64.
- Disk probe: passed; `/` has 99G total, 45G used, 50G available, 48% used.
- Agent Host service probe: passed; `kolibri-agent-host.service` is loaded,
  enabled, active, and running.
- Compile probe: passed.
- Factory preflight: passed with `factory_control_runtime_preflight=ok`.
- Focused pytest: passed with `37 passed in 32.77s`.
- Git remote read probe: passed for `origin HEAD`; remote `HEAD` resolves to
  `refs/heads/main` at commit `f7ac32c70406432a52752ca45d87e35d9f1facd3`.
- Task branch remote probe: command succeeded but returned no matching remote
  branch for `agent/P0_UIAP_RAG_NODE_TOOLING_LIGHT_REPAIR_2026_07_02/generic`.

Not run:

- Full pytest suite.
- Frontend `npm install` or build.
- Heavy RAG indexing, embeddings batches, model serving, GPU checks, or service
  restart checks.


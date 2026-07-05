# Result

Task: P0_CANONICAL_RUN_ARTIFACT_CONTRACT_AND_ALIASES_2026_07_01

Status: completed locally, ready for PR #83 branch publication.

Remote result fields:

- Task ID: `P0_CANONICAL_RUN_ARTIFACT_CONTRACT_AND_ALIASES_2026_07_01`
- Node: `kolibri`
- Russian agent display name: `Автономный инженер`
- Branch: `p0/agent-host-runner-contract-hardening-2026-06-30`
- PR: `#83`
- Base/source SHA: `c837e93ee3bf9da3c07b806ebfc003f52b9ad8d5`
- Tests: `python3 -m pytest tests/test_agent_host_runner_contract.py -q` passed, `20 passed`; `python3 -m pytest tests/test_agent_host_runner_contract.py tests/test_agent_host_telegram_chat.py tests/test_agent_host_image_generation.py -q` passed, `26 passed`; `python3 -m compileall -q ops/agent_host.py` passed
- Blockers: none known
- Next task: publish the commit to PR #83 after final review
- New head SHA: reported in the final control-plane response after local commit creation

Implemented:

- Canonical run artifact directory envelope support via `canonical_run_artifact_dir`, `run_artifact_dir`, and `run_artifacts_dir`.
- Exact required run artifacts: `PLAN.md`, `ACTIONS.md`, `TESTS.md`, `RESULT.md`, and `NEXT.md`.
- Canonical artifacts are machine-enforced through existing required artifact lists and blockers.
- Missing `NEXT.md` blocks completion.
- Near-miss directories are ignored unless listed as explicit aliases.
- Complete explicit aliases are logged, deterministic, and materialized into the canonical directory.
- Publish preflight inherits the finalizer blocker behavior, so failed artifact verification blocks push.

Changed files:

- `ops/agent_host.py`
- `tests/test_agent_host_runner_contract.py`
- `docs/agent/AGENT_RUNNER_CONTRACT.md`
- `docs/agent/runs/2026-07-01-p0-canonical-run-artifact-contract-and-aliases/PLAN.md`
- `docs/agent/runs/2026-07-01-p0-canonical-run-artifact-contract-and-aliases/ACTIONS.md`
- `docs/agent/runs/2026-07-01-p0-canonical-run-artifact-contract-and-aliases/TESTS.md`
- `docs/agent/runs/2026-07-01-p0-canonical-run-artifact-contract-and-aliases/RESULT.md`
- `docs/agent/runs/2026-07-01-p0-canonical-run-artifact-contract-and-aliases/NEXT.md`

Risk:

- Alias materialization copies only missing canonical files and does not overwrite existing canonical files. This avoids replacing user-authored canonical outputs, but it also means a stale existing canonical file is not reconciled by alias content.

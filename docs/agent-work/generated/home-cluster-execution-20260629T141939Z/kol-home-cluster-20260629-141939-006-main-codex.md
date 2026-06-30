# FormulaLM Remote Benchmark Preflight

Task id: `KOL-HOME-CLUSTER-20260629-141939-006-MAIN-CODEX-DELIVERABLE-RETRY`
Role slot: `codex-slot-6`
Generated: `2026-06-30T11:20:53Z`

## Goal

Prepare a remote-only preflight artifact for a FormulaLM/Qwen/model benchmark without running the benchmark on a Mac or in this local worktree.

The benchmark execution boundary is:

- Allowed target: remote Linux node with the Home training/inference environment.
- Disallowed target: local Mac or this checked-out repository session.
- This artifact is documentation and execution readiness evidence only; it does not download models, install benchmark dependencies, invoke Qwen/FormulaLM, or run local inference.

## Implementation Delta

Created this generated preflight report as the deliverable artifact. No benchmark code path was added because the repository currently exposes Qwen training utilities and backend benchmark-history stubs, but no concrete FormulaLM benchmark runner or safe write-scope contract for a runner implementation.

Concrete delta:

- Added a remote-only benchmark preflight report with execution boundaries, repo surface review, verification log, risks, and Telegram-ready fallback summary.
- Recorded that no local model benchmark command was executed.
- Recorded the report itself as the Control Plane result reference.

## Touched Paths

- `docs/agent-work/generated/home-cluster-execution-20260629T141939Z/kol-home-cluster-20260629-141939-006-main-codex.md`

## Repo Surface Reviewed

- `README.md`: documents the Kolibri cluster topology, including Home as Training Hub and remote server roles.
- `scripts/training/README.md`: documents Qwen2.5 LoRA training scripts and notes that dependency/model access must be available on the target host.
- `scripts/training/finetune.py`: Qwen training entry point; not invoked.
- `scripts/training/merge_adapter.py`: adapter merge entry point; not invoked.
- `backend/routes_v1.py` and `backend/adapter.py`: benchmark-history endpoints are stubs; no FormulaLM runner found.
- `ops/agent_host.py` and `ops/factory_control.py`: Control Plane result contract reviewed for result-reference shape.

## Remote Linux Preflight Checklist

Use this checklist on the remote Linux benchmark node before any FormulaLM/Qwen benchmark execution:

1. Confirm host identity and OS:
   - `uname -a`
   - `python3 --version`
   - `nvidia-smi || true`
2. Confirm the benchmark is not being launched from a Mac:
   - `test "$(uname -s)" = Linux`
3. Confirm repository revision and clean benchmark inputs:
   - `git rev-parse --abbrev-ref HEAD`
   - `git rev-parse HEAD`
   - `git status --short`
4. Confirm dependency plan without leaking credentials:
   - Use a configured mirror/proxy if outbound package access is restricted.
   - Do not print tokens, `.env`, auth caches, SSH keys, or private environment values.
5. Confirm model/cache placement on the remote node:
   - Keep Hugging Face, Qwen, FormulaLM, GGUF, or adapter caches outside the repo unless explicitly documented.
   - Do not commit generated model weights or benchmark outputs.
6. Confirm output contract:
   - Save benchmark logs and machine-readable result JSON under the Control Plane artifact directory.
   - Return `result_reference`, `changed_files`, `checks`, and commit or PR evidence.

## Verification Log

Commands executed for this artifact-only preflight:

- `git status --short --branch`
  - Result: passed; branch `codex/kol-home-cluster-20260629-141939-006-main-codex` with only this new generated docs artifact pending.
- `rg -n "FormulaLM|Qwen|benchmark|bench|preflight|remote|Mac|macOS|model" -g '!**/.env*' -g '!**/.ssh/**' -g '!**/.mimocode/**' -g '!**/*token*' -g '!**/*auth*' .`
  - Result: passed; reviewed Qwen training scripts, benchmark-history stubs, and Control Plane result contract. No FormulaLM benchmark runner found.
- `python -m pytest tests/test_factory_runtime_contracts.py tests/test_agent_host_telegram_chat.py::test_parse_codex_agent_message_jsonl tests/test_telegram_gateway.py::test_owner_remote_task_completion_returns_clean_url_result`
  - Result: blocked by environment; `/bin/bash: python: command not found`.
- `python3 -m pytest tests/test_factory_runtime_contracts.py tests/test_agent_host_telegram_chat.py::test_parse_codex_agent_message_jsonl tests/test_telegram_gateway.py::test_owner_remote_task_completion_returns_clean_url_result`
  - Result: blocked by environment; `/usr/bin/python3: No module named pytest`.
- Direct Python harness for focused test functions:
  - Result: passed; six checks passed:
    - `test_factory_runtime_contracts.test_task_envelope_schema_and_idempotency_key`
    - `test_factory_runtime_contracts.test_heartbeat_payload_schema`
    - `test_factory_runtime_contracts.test_result_envelope_schema`
    - `test_factory_runtime_contracts.test_lease_expiry_calculation`
    - `test_telegram_gateway.test_owner_remote_task_completion_returns_clean_url_result`
    - `test_agent_host_telegram_chat.test_parse_codex_agent_message_jsonl`
- `python3 -m py_compile ops/agent_host.py ops/factory_control.py ops/telegram_gateway.py scripts/training/finetune.py scripts/training/merge_adapter.py backend/routes_v1.py backend/adapter.py`
  - Result: passed.
- `bash -n scripts/training/run_pipeline.sh`
  - Result: passed.
- `git diff --cached --check`
  - Result: passed; staged artifact diff has no whitespace errors.

No FormulaLM, Qwen, model download, training, inference, or benchmark command was executed locally.

## Control Plane Result

- `result_reference`: `docs/agent-work/generated/home-cluster-execution-20260629T141939Z/kol-home-cluster-20260629-141939-006-main-codex.md`
- `status`: `completed`
- `kind`: `remote_benchmark_preflight_artifact`
- `local_benchmark_run`: `false`
- `mac_execution`: `false`

## Risks

- No FormulaLM-specific benchmark runner is present in the repository, so this artifact cannot validate FormulaLM invocation flags.
- Remote package/model access may require a proxy or mirror, as the training README already notes restricted outbound access.
- Hardware readiness is not proven by this local preflight; GPU/CPU/memory checks must run on the remote Linux node.
- Benchmark result quality is not assessed here because no benchmark was executed.

## Telegram Summary

Fallback agent-message:

FormulaLM remote benchmark preflight is ready as a repo artifact. I did not run any model benchmark locally or on a Mac. The report records the remote Linux execution boundary, reviewed repo paths, verification commands, risks, and Control Plane result reference: `docs/agent-work/generated/home-cluster-execution-20260629T141939Z/kol-home-cluster-20260629-141939-006-main-codex.md`.

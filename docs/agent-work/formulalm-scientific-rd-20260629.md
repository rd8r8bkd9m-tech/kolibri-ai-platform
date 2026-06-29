# FormulaLM Scientific R&D 2026-06-29

Task: `KOL-FORMULALM-SCIENTIFIC-RD-20260629`  
Role: `Исследователь FormulaLM`  
Result reference: `docs/agent-work/formulalm-scientific-rd-20260629/`  
Verdict: `blocked`

## Executive Summary

The remote guard was executed on a Linux node before any model call. The
preflight artifact was written first, then the runtime/model gate stopped the
benchmark because no supported local runtime responded.

No FormulaLM, Qwen, QW 2.5, Ollama generation, llama.cpp, vLLM, or model
benchmark was run on macOS. No benchmark result was synthesized.

## Evidence

- Preflight: `docs/agent-work/formulalm-scientific-rd-20260629/preflight.json`
- Blocker JSON: `docs/agent-work/formulalm-scientific-rd-20260629/blockers.json`
- Blocker report: `docs/agent-work/formulalm-scientific-rd-20260629/blocker-report.md`
- Dataset artifact: `docs/agent-work/formulalm-scientific-rd-20260629/dataset.jsonl`

Preflight highlights:

| Field | Value |
| --- | --- |
| Platform | `Linux` |
| Hostname | `kolibri` |
| Uname | `Linux kolibri 6.8.0-36-generic #36-Ubuntu SMP PREEMPT_DYNAMIC Mon Jun 10 10:49:14 UTC 2024 x86_64 x86_64 x86_64 GNU/Linux` |
| Model candidate | `qwen2.5-coder:3b` |
| Dataset version | `formulalm-estimate-ru-2026q2-v1` |
| Pricebook version | `kolibri-ru-2026q2-v1` |
| Artifact dir | `docs/agent-work/formulalm-scientific-rd-20260629` |

Blocker:

| Severity | Category | Message |
| --- | --- | --- |
| `P1` | `missing_model_runtime` | `Ollama runtime did not respond before benchmark start: <urlopen error [Errno 111] Connection refused>` |

## Harness Work

`scripts/formulalm_benchmark.py` was extended so the next runtime-ready run
records the H1-H5 contract:

| Metric | Status |
| --- | --- |
| `unique_output_hashes_per_case` | implemented |
| `parse_error_rate` | implemented |
| `runtime_error_rate` | implemented |
| `formula_consistency_rate` | implemented |
| `latency_p50_ms` / `latency_p95_ms` | implemented |
| `blocked_reason_count` | implemented |
| `manual_fix_count` | implemented as automatic QA-required count; independent QA remains a P2 blocker for H5 proof |

Baseline and FormulaLM modes use the same model, dataset, runtime endpoint and
generation settings. FormulaLM differs only by applying the deterministic
estimate kernel after the same base model extracts variables.

## Verification

- `python3 -m compileall -q scripts/formulalm_benchmark.py backend/estimate_engine.py tests/test_formulalm_benchmark.py`
- `python3 -m pytest -q tests/test_formulalm_benchmark.py` failed because `pytest` is not installed in this node.
- Direct test execution passed by importing `tests.test_formulalm_benchmark` and calling all `test_*` functions.
- JSONL validation passed for 12 dataset lines.
- Runtime-gated benchmark command returned blocker exit code `2` and wrote `preflight.json` before `blockers.json`.

## Next Plan

1. Restore or install one supported remote runtime on the leased Linux node:
   Ollama, llama.cpp, vLLM, or a documented compatible endpoint.
2. Pull or register `qwen2.5-coder:3b` or the owner-approved Qwen/QW 2.5 model.
3. Re-run smoke: 5 cases x 2 repeats.
4. Re-run pilot with the maximum available dataset, targeting 20 cases x 5
   repeats after dataset expansion.
5. Add independent QA review artifact before claiming H5.

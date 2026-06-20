# Kolibri Agent Protocol

This repository is operated with Codex as the chief orchestrator and reviewer.
MiMo Code and other remote agents are bounded executors. They may inspect,
prepare, and implement scoped tasks, but merge, deploy, scaling, and release
decisions require Codex review.

## Objectives

### Track A: Agent Platform Hardening

- Keep all agent work in branch/worktree isolation.
- Run MiMo through `scripts/mimo_task_runner.py` or a manifest-backed wrapper.
- Preserve structured results: `status`, `summary`, `changed_files`, `checks`,
  `risks`, and `artifacts`.
- Prove no secrets are copied into prompts, logs, run artifacts, or repo files.

### Track B: FormulaLM Estimate Pilot

- Run `formulalm-proof-v1` before the full 19-server pilot when the goal is a
  short scientific proof. It uses four servers, frozen Qwen2.5-1.5B logits,
  three FormulaLM seeds, and untouched-test full-vocabulary CE.
- Start with run ID `estimate-pilot-001`.
- Use only the current 401-421 estimate dataset for the first pilot.
- Run preflight before any training: inventory, dataset manifest, schema audit,
  duplicate/PII/leakage checks, canonical JSON proposal, and grouped splits.
- Use 19 server roles from `ops/experiments/estimate-pilot-001/role_map.json`.

### Track C: Benchmark and Scale Decision

- Compare FormulaLM islands, retrieval baseline, frozen Transformer baseline,
  reranker output, deterministic validator, and independent final-test scoring.
- Do not scale to 10k, 100k, or 1M estimates until `estimate-pilot-001` has a
  final STOP/CONTINUE/SCALE report with metrics and artifact hashes.

## Gated Scaling

1. **Hardening**: runner, manifests, forbidden paths, log redaction, SSH argv,
   and no unsafe permissions.
2. **Preflight**: all 19 servers inventoried, dataset manifest created, splits
   proven non-leaking, and role map validated.
3. **Read-only fanout**: every healthy server receives one read-only task and
   returns a structured result with zero diff.
4. **Controlled mutation**: one small task on one server in an isolated worktree.
   Codex reviews diff and checks before merge.
5. **24/7 queue**: only after the previous gates pass.

## Data Integrity Rules

- Source estimate files are immutable. Derived artifacts must live under the run
  directory.
- The source estimate files are immutable for `estimate-pilot-001`.
- Every input file used by the pilot must have a SHA-256 entry in
  `dataset_manifest.json`.
- Final-test data must not appear in prompts, training shards, retrieval index
  construction, or manual tuning notes.
- PII audit and duplicate audit are required before train/validation/final-test
  splits are accepted.
- Any schema coercion must be recorded in a transform log.

## Run Directory Contract

The canonical remote run directory is:

```text
/srv/kolibri/runs/estimate-pilot-001/
```

Required subpaths:

- `input/`: immutable source snapshots or references.
- `manifests/dataset_manifest.json`: SHA-256 dataset manifest.
- `manifests/config_hashes.json`: hashes for configs, prompts, role maps.
- `status/*.json`: per-server heartbeat and task state.
- `logs/`: redacted worker logs.
- `metrics/`: training, evaluation, latency, and throughput metrics.
- `artifacts.json`: index of produced artifacts and hashes.
- `checkpoints/`: model/checkpoint hashes, not secrets.
- `reports/final_report.md`: STOP/CONTINUE/SCALE decision.

## Safety Rules

- Never read or log `.env`, `.ssh`, `.mimocode`, `auth.json`, tokens,
  passwords, private keys, VPN credentials, or provider credentials.
- Do not read or log secrets.
- Never use `--dangerously-skip-permissions`.
- Never run broad destructive commands such as `pkill`, `rm -rf` outside a
  task-owned run directory, `git reset --hard`, or service restarts unless the
  prompt explicitly authorizes the exact target.
- Never deploy or restart production services from a MiMo worker.
- Do not mutate global memory, deployed paths, or source datasets during
  read-only and preflight tasks.

## Worker Communication

Workers receive a task envelope following
`ops/formulalm/task_envelope.schema.json`. They write status updates following
`ops/formulalm/status.schema.json` and final results following
`ops/formulalm/result.schema.json`.

Workers must stop and report `blocked` when a task requires credentials,
production mutation, missing dataset evidence, or access outside `allowed_paths`.

## Decisions

- **STOP**: leakage, missing metrics, failed safety gate, dataset mutation,
  unreviewed deploy, or incomplete final-test evidence.
- **CONTINUE**: gates passed but pilot evidence is insufficient for scaling.
- **SCALE**: pilot metrics, hashes, logs, independent final-test evaluation, and
  risk review support expanding the dataset or agent pool.

## Final Report Requirements

The final report must include:

- run ID, commit, role map hash, prompt/config hashes;
- server participation and health summary;
- dataset manifest summary and split proof;
- model/baseline metrics and validation/final-test separation;
- changed files and artifacts with hashes;
- risks, blockers, incident notes, and mitigations;
- explicit STOP/CONTINUE/SCALE decision.

Success requires metrics. A worker or orchestrator must not claim success from
logs, plausible output, or a completed process alone.

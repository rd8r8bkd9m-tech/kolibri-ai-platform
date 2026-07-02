# MVP Runtime Path

Date: 2026-07-02

Internal factory for Vladislav and agents:

`submit -> lease -> execute -> heartbeat -> artifacts -> status -> collect`

## Path

1. `submit`: Mac or any trusted command node submits an envelope through the Fabric API or dispatcher CLI.
2. `lease`: Factory Control Plane selects a compatible Agent Host and grants a time-limited lease.
3. `execute`: Agent Host runs the requested runner: MIMO, Codex, API/local model, generic subprocess, FormulaLM/crawler-like task, or another registered runner.
4. `heartbeat`: Agent Host refreshes the task lease while execution is active.
5. `artifacts`: Runner writes `result.json`, logs, and structured failure artifacts when needed.
6. `status`: Dispatcher and API status expose task state, lease status, and heartbeat status.
7. `collect`: Owner or dispatcher collects final result reference and artifacts.

## Current Guardrail

Large requeue operations are gated behind a canary. MIMO and FormulaLM crawler requeue must wait until the deployed Agent Host and Control Plane show live heartbeat renewal and zero premature `dead_letter` transitions for canary tasks.

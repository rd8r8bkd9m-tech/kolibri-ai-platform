# Next

1. Restore authoritative Control Plane reachability without deleting queue state.
2. Re-run `GET /v1/health`, `GET /v1/fleet/nodes`, `GET /v1/tasks/queue/diagnostics`.
3. Submit one bounded `read_only_probe` or docs runner task through `POST /v1/tasks/submit`.
4. Poll `GET /v1/tasks/{task_id}/status` until terminal.
5. Collect `GET /v1/tasks/{task_id}/artifacts` and verify the artifact file is readable and content-bearing.

FormulaLM next:

1. Keep the 10-question v1 benchmark fixed.
2. Add tokenizer/checkpoint compatibility repair.
3. Measure latency, CPU, RAM and keep FormulaLM hardware-aware.

# RESULT

Status: completed with local dependency limitation for full pytest

Implemented scoped lease-heartbeat repair for long-running Agent Host runner paths and Factory Control Plane lease visibility.

Coverage:

- Direct MIMO path: covered by shared JSON runner heartbeat monitor.
- Codex path: covered by shared JSON runner heartbeat monitor.
- API/local model path: covered by shared long-running heartbeat monitor.
- FormulaLM/crawler-like path: covered as API/local or generic long-running runner pattern.
- Generic subprocess path: covered by `run_command()` heartbeat monitor and existing pid heartbeat loop.
- Image/model long-running path: covered for configured subprocess and OpenAI image API runner.

Requeue decision:

Do not requeue the MIMO wave or FormulaLM crawler wave before validation. Run a 3-task canary first and require multiple heartbeat renewals, zero premature `lease_expired`, structured artifacts, and final terminal states.

Validation:

- Focused Agent Host runner contract tests passed.
- Focused direct MIMO tests passed.
- Focused factory runtime tests passed.
- Full pytest was blocked during collection by missing local dependencies: `pydantic` and `httpx`.

Git/GitHub:

- Local commit created.
- Push failed because the SSH key on this server is marked read-only.
- Draft PR was not opened because the branch could not be pushed.

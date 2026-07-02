# PR119_RELEASE_GATE

Decision: blocked

PR:

- URL: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/119
- State: open, draft, unmerged.
- Head branch: `p0/agent-host-long-runner-lease-heartbeat-repair-2026-07-02-clean`
- Head commit: `1aab1a2833965a5e9c70dbe685c9d3e85849f070`
- Base: `main` at `f7ac32c70406432a52752ca45d87e35d9f1facd3`
- Mergeable according to connector: true.
- Reviews: none.
- Status contexts: none reported.

Allowed-scope check:

- Changed files are limited to Agent Host, Factory Control, focused tests, and docs/artifacts.
- No frontend, PWA, billing, Telegram UX, FormulaLM feature/model gateway, PR #46, qjns, or uiap scope found.
- No product code changes beyond PR119 lease-heartbeat/control-plane status logic.

Secrets check:

- No secret values found in changed implementation/docs by targeted scan.
- Test fixture string `SECRET_REFRESH_TOKEN_123` is synthetic and is asserted not to leak into serialized outputs.
- Environment variable names such as `OPENAI_API_KEY`, `KOLIBRI_API_RUNNER_TOKEN`, and `TELEGRAM_BOT_TOKEN` are code references, not secret values.

Heartbeat coverage:

- Direct MIMO: covered by `run_direct_mimo_task` through `run_json_payload_command` and shared `long_running_heartbeat`.
- Codex: covered by `run_requested_ai_runner` and `run_json_text_command`.
- API/local model: covered by `run_requested_ai_runner` wrapping API/local calls in `long_running_heartbeat`.
- Generic subprocess: covered by `run_command` heartbeat loop with process pid.
- FormulaLM/crawler-like: covered through API/local/generic long-running runner patterns and focused crawler-like test.
- Structured `lease_heartbeat_failed`: present in Agent Host error handling and covered by focused test.
- Factory Control refreshes expired leases with fresh heartbeat instead of premature dead-lettering.

Blockers:

- PR #119 is still draft.
- No review approval is present.
- No CI/status contexts are reported for the head commit, so CI green cannot be proven.
- Full local pytest is blocked by missing `pydantic` and `httpx`.
- Live primary-candidate Control Plane health/status probes timed out and recent logs show lease 500s.

Result:

The PR implementation is locally test-clean for the targeted gate, but the release gate cannot be marked merge-ready until PR draft/review/CI status and Control Plane health are resolved.

# Plan

Status: `in_progress_blocked_on_live_control_plane`

Goal: make owner command `СТАРТ ФАБРИКИ` map to a task id, Control Plane dispatch, Agent Host execution, heartbeat/status, collectable artifact and owner report.

Steps:

- Work only from clean checkout `/srv/kolibri-ai-platform`.
- Use branch `p0/governing-chat-mcp-action-start-factory-20260704`.
- Add thin ChatGPT Action gateway adapter without duplicating queue logic.
- Add OpenAPI contract for ChatGPT Action/MCP style invocation.
- Prove live Start Factory MVP if Control Plane is reachable.
- If live proof is blocked, document exact blocker and repair task without faking completion.

FormulaLM parallel track:

- Repro suite: `/srv/kolibri/formulalm-tests`.
- Baseline report: `/srv/kolibri/formulalm-tests/reports/formulalm_repro_eval_v1.json`.
- Baseline: aggregate `0.066391`, exact `0/10`, contains `0/10`, tokenizer mismatch `155 -> 64`.

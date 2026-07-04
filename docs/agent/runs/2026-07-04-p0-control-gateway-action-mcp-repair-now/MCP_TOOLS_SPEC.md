# MCP_TOOLS_SPEC

All tools call the HTTP Kolibri Control Gateway. Auth is Bearer token via `KOLIBRI_CHATGPT_ACTION_TOKEN`.

Output schema for every tool is `GatewayResponse`:

```json
{
  "status": "completed|running|blocked|failed|partial",
  "request_id": "string",
  "task_id": "string",
  "control_plane_used": "string",
  "artifacts": [],
  "blocked_reason": "string",
  "fallback_nodes": [],
  "repair_task": "",
  "next_action": "string"
}
```

## kolibri_factory_start

Input schema:

```json
{"autopilot":"A1|A2","runner":"codex|mimo|api|local_llm","mode":"canary|dry_run","submit_canary":true}
```

Calls internally: `POST /v1/factory/start`.

Approval required: no for canary/dry-run; yes if request text contains dangerous operations.

Dangerous: no by default.

## kolibri_director_tick

Input schema:

```json
{"tick_id":"string","scope":"status_only"}
```

Calls internally: `POST /v1/director/tick`.

Approval required: no.

Dangerous: no.

## kolibri_fleet_status

Input schema:

```json
{}
```

Calls internally: `GET /v1/fleet/status`.

Approval required: no.

Dangerous: no.

## kolibri_queue_status

Input schema:

```json
{}
```

Calls internally: `GET /v1/queue/status`.

Approval required: no.

Dangerous: no.

## kolibri_task_submit

Input schema:

```json
{"kind":"string","objective":"string","runner":"codex|mimo|api|local_llm","target_node":"string","required_capability":"string","constraints":{},"write_scope":[]}
```

Calls internally: `POST /v1/tasks/submit` -> Control Plane `/v1/agents/tasks`.

Approval required: no for read-only diagnostic/docs/review tasks; yes for deploy, merge, Redis, secrets, service lifecycle, broad rollout.

Dangerous: depends on task body.

## kolibri_task_status

Input schema:

```json
{"task_id":"string"}
```

Calls internally: `GET /v1/tasks/{task_id}/status`.

Approval required: no.

Dangerous: no.

## kolibri_task_artifacts

Input schema:

```json
{"task_id":"string"}
```

Calls internally: `GET /v1/tasks/{task_id}/artifacts`.

Approval required: no.

Dangerous: no.

## kolibri_github_prs

Input schema:

```json
{}
```

Calls internally: `GET /v1/github/prs`.

Approval required: no for read-only PR status.

Dangerous: no.

Current HTTP gateway returns `partial` until a safe PR index backend is bound; it does not read local GitHub secrets or shell out to `gh`.

## kolibri_request_approval

Input schema:

```json
{"action":"string","reason":"string","target":"string","risk":"string"}
```

Calls internally: `POST /v1/approvals/request`.

Approval required: this tool creates the approval request.

Dangerous: no execution happens inside the tool.

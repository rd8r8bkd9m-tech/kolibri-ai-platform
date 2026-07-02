# Kolibri Factory — полный пакет промптов

Дата сборки: 2026-07-01  
Владелец: Кочуров Владислав Евгеньевич  
Назначение: единый файл с промптами, которые можно перенести в документацию проекта, холст, `docs/superfactory/`, `docs/agent/` и использовать для постановки задач агентам.

> Важно: устаревшая трактовка “Mac = dev station” заменена на новую: **Mac = тонкий интеллектуальный клиент / командный пульт**, а реальная работа выполняется удалённой фабрикой. **Primorye и Home** — полноценные command/control серверы и fallback-узлы. Основная связь между серверами и агентами должна идти через **единый API-first / OpenAI-compatible Fabric API**.

---

## Индекс

0. MASTER CANVAS — главный холст цели
1. Owner Policy V2 — Mac thin client, remote factory executor
2. API-first full-control fabric — короткий addendum
3. P0 Unified Fabric API and Server Connectivity
4. P0 Command Fabric HA and Any-Node Control
5. P0 OpenAI-Compatible Fabric API Standard
6. Dispatch P0 Runner Hardening to Remote Factory
7. P0 Agent Host Generic Runner Contract Hardening
8. P0 GitHub Operating System for Kolibri Factory
9. P0 Public Site and Backend Vertical Audit
10. P0 Superfactory Documentation Package
11. P0 Fleet Resource Inventory and Reachability
12. P0 Repair Degraded Server Readiness
13. P0 Preserve Dirty Runtime Diffs
14. P1 Skill Registry and Internet Discovery
15. P1 Agent Team Mesh and Human Language Protocol
16. P1 Anti-Degradation System
17. P1 Rerun Integration Contract Audit
18. P1 Split PR #46
19. P1 Server Skill Sync
20. P2 100K Logical Agent Scheduler
21. P2 Local LLM Ring and Sovereign Model Factory
22. P2 Business Builder and Revenue Engine
23. P2 Phone / Video Relay Observation Policy
24. P3 Video Avatar Meeting Layer
25. P3 Full Autopilot START Specification
26. Kwork Revenue Manager subagent
27. Short emergency snippets

---

# 0. MASTER CANVAS — главный холст цели

```text
KOLIBRI SUPERFACTORY CANVAS — MASTER PLAN

Owner:
Кочуров Владислав Евгеньевич.
Role:
Chief Visionary, Owner, Lead Developer, Final Authority.

Project:
Kolibri Factory — distributed AI/platform factory.

Current known state:
- GitHub is source of truth for branches, PRs, CI, issues, releases and project history.
- Mac is a thin intelligent command client: it thinks, plans, prepares prompts/envelopes, dispatches tasks, observes statuses and collects reports.
- Mac is NOT the main execution/development machine.
- Primorye is a primary/high-priority server command/control node and may also execute heavy tasks.
- Home is a reserve command/control node and owner recovery point.
- main and primary-candidate are runtime/control nodes.
- Telegram, phone, GitHub emergency mode and any trusted server/computer may act as command entrypoints.
- Heavy execution, tests, Linux/runtime validation, local LLMs, FormulaLM, image generation and agents run on remote servers / Control Plane / GitHub Actions / server agents.
- Control Plane sees 20 server node cards.
- Some nodes are degraded and must be classified, not hidden.
- GitHub must remain always current.

Global objective:
Build Kolibri into a self-developing, distributed, sovereign AI factory with:
- unified API-first / OpenAI-compatible fabric between all servers and agents;
- command/control from any trusted node;
- strict runner contract;
- GitHub operating system;
- fleet resource usage;
- skill registry;
- team mesh;
- local LLM ring;
- FormulaLM integration;
- business/revenue engine;
- video-avatar meeting layer;
- anti-degradation system;
- eventual full autopilot command.

Non-negotiable rules:
- No secrets printed.
- No push to main.
- No force push.
- No destructive git commands.
- No deleting dirty work.
- No fake completed status.
- No claiming tests passed if unavailable.
- No blind install of unaudited internet code on servers.
- No abusing free resources or violating Terms of Service.
- No automatic money movement or bank actions without owner approval.
- No use of phone/video relay for 2FA, bank approvals, security bypass or financial confirmation.

Execution order:
1. Unified API-first Fabric API and server connectivity.
2. Command Fabric HA and any-node control.
3. OpenAI-compatible internal API standard.
4. Dispatch P0 runner hardening to remote factory.
5. Harden Agent Host generic runner contract.
6. GitHub Operating System.
7. Fleet resource inventory.
8. Repair degraded nodes and server GitHub auth.
9. Preserve dirty runtime diffs.
10. Superfactory documentation package.
11. Skill registry and discovery.
12. Agent team mesh.
13. Anti-degradation system.
14. Integration contract audit.
15. PR #46 split.
16. Server skill sync.
17. 100K logical agents scheduler.
18. Local LLM ring and sovereign model factory.
19. Business/revenue engine.
20. Phone/video relay policy.
21. Video avatar meetings.
22. Future START full autopilot spec.

Every task must produce:
- PLAN.md
- ACTIONS.md
- TESTS.md
- RESULT.md
- NEXT.md

Every real remote task must have:
- task_id;
- envelope;
- target node pool;
- status;
- lease owner if available;
- result artifact;
- human-readable report.
```

---

# 1. Owner Policy V2 — Mac thin client, remote factory executor

```text
TASK: UPDATE_KOLIBRI_GOAL_TO_MAC_THIN_CLIENT_REMOTE_FACTORY

You must update the project goal.

Old wording that said Mac is `dev_station_and_command_center` and `mac_development_allowed: true` is now superseded by Owner Policy V2.

New owner policy:
Mac is a thin intelligent client only.
Mac thinks, plans, creates envelopes, dispatches remote tasks, watches statuses, collects artifacts and reports to the owner.
Mac must not act as the main local developer.
All real development, tests, validation, server checks, MIMO/API agents, local LLM work, FormulaLM, image generation and heavy work must run in the remote Kolibri Factory.

Do not rewrite historical digest.
Create a superseding policy document.

Create/update:
- docs/agent/OWNER_POLICY_V2_MAC_THIN_CLIENT_REMOTE_FACTORY.md
- docs/agent/dispatcher/README.md
- docs/agent/dispatcher/QUEUE.md
- docs/agent/dispatcher/DISPATCH_LOG.md
- docs/superfactory/00_GOAL.md
- docs/superfactory/20_ROADMAP.md
- docs/superfactory/TASKS.md

Required content:
1. State clearly that Mac is a thin intelligent dispatcher.
2. State that remote factory is the executor.
3. State that GitHub is source of truth.
4. State that every real task needs task_id, envelope, remote status and result artifact.
5. State that local implementation on Mac is forbidden unless explicitly approved as an exception.
6. State that all future prompts must dispatch work to remote agents first.
7. State that old `mac_development_allowed: true` wording is superseded.

Do not modify product code.
Do not run tests.
Do not push to main.
Do not print secrets.

Final response must include:
- files created/updated;
- old goal superseded yes/no;
- new goal summary;
- next remote dispatch task;
- exact envelope path for P0 runner hardening.
```

---

# 2. API-first full-control fabric — короткий addendum

```text
ADDENDUM: API-FIRST FULL-CONTROL FABRIC

Owner correction:
Связь между всеми серверами и агентами должна держаться полностью по единому защищённому API.
SSH не является основным способом работы. SSH разрешён только для bootstrap, аварийного восстановления и диагностики.

Goal:
Создать Kolibri API-first control fabric, где с любого command node — Mac, Primorye, Home, main, primary-candidate, Telegram, phone или любого доверенного компьютера — можно через один API:
- видеть все серверы;
- видеть все агенты;
- видеть все модели;
- ставить задачи;
- запускать удалённую разработку;
- запускать тесты;
- читать статусы;
- получать артефакты;
- управлять сервисами;
- маршрутизировать задачи через fallback nodes;
- добавлять новые серверы в сеть.

Core rule:
Agent must never answer “server unavailable” as a dead end.
If direct route fails, agent must use API relay/fallback route and return structured status.

Use API-first paths:
- command node → Kolibri Fabric API
- Fabric API → Control Plane
- Control Plane → Agent Host
- Agent Host → remote agents / MIMO / API agents / local LLM / tools
- results → artifacts → GitHub/owner report

Required API endpoints:
- GET  /v1/health
- GET  /v1/fleet/nodes
- GET  /v1/fleet/topology
- GET  /v1/fleet/route
- GET  /v1/fleet/capabilities
- GET  /v1/models
- POST /v1/responses
- POST /v1/chat/completions
- POST /v1/agents/tasks
- GET  /v1/agents/status/{task_id}
- GET  /v1/agents/artifacts/{task_id}
- POST /v1/agents/cancel/{task_id}
- POST /v1/admin/exec
- POST /v1/admin/service
- POST /v1/admin/git
- POST /v1/admin/bootstrap-node
- POST /v1/admin/rotate-keys

Full rights policy:
The owner may issue full-control commands through API, but every privileged action must be:
- authenticated;
- authorized;
- traceable;
- signed or token-bound;
- logged;
- reversible when possible;
- scoped by task_id;
- protected from secret leakage.

Do NOT use one eternal shared key.
Create a trust plane:
- per-node identity;
- mTLS or signed service tokens;
- WireGuard/mesh VPN if useful;
- short-lived owner/admin tokens;
- rotating node tokens;
- emergency break-glass token;
- API key/cert rotation policy;
- no secrets in logs;
- no hardcoded credentials.

Create/update docs:
- docs/superfactory/API_FIRST_CONTROL_FABRIC.md
- docs/superfactory/FULL_CONTROL_API_POLICY.md
- docs/superfactory/NODE_IDENTITY_AND_KEY_ROTATION.md
- docs/superfactory/API_FALLBACK_ROUTING_POLICY.md
- docs/superfactory/ANY_NODE_API_ACCESS_RUNBOOK.md
- docs/superfactory/NEW_SERVER_API_BOOTSTRAP.md
- docs/superfactory/ADMIN_API_SECURITY_GATES.md
- docs/superfactory/TASKS.md

Acceptance:
- SSH is documented as emergency/bootstrap only.
- API is documented as the primary control plane.
- Every server can be controlled through API or fallback API relay.
- Agent never returns dead-end “server unavailable”.
- Full owner rights exist through API but are authenticated, scoped, logged and rotated.
- New servers can be added by bootstrap API contract.
- No secrets are printed.
- No destructive action is executed in this task.
```

---

# 3. P0 Unified Fabric API and Server Connectivity

```text
TASK: P0_KOLIBRI_UNIFIED_FABRIC_API_AND_SERVER_CONNECTIVITY

Priority:
P0 — this is the first foundation task.

Goal:
Create the unified Kolibri Fabric API and server connectivity backbone so every command node, server, agent, MIMO/API runner, local LLM service, Telegram gateway and future FormulaLM service communicates through one OpenAI-compatible API contract.

Owner intent:
The factory already exists. The problem is that connectivity and protocols are not unified enough.
The owner must be able to send a task from Mac, Primorye, Home, Telegram, phone, main, primary-candidate or any trusted computer/server.
The receiving agent must understand the same task shape, know the whole fleet state, route work to healthy nodes, and return structured status/artifacts.

Core principle:
No more isolated formats.
No more “I cannot reach that server” as a dead-end answer.
Every failure must become structured:
- node;
- status;
- reason;
- fallback route;
- next repair task.

Read first:
- docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/GLOBAL_DIGEST_FOR_CHATGPT.md
- ops/factory_control.py
- ops/agent_host.py
- ops/kolibri-dispatch
- ops/telegram_gateway.py
- ops/mesh_control_bridge.py
- backend/providers.py
- backend/adapter.py
- backend/pipeline.py
- README.md
- .github/workflows/ci.yml

Main design:
Kolibri Fabric API must expose or define these endpoints:

Health and discovery:
- GET /v1/health
- GET /v1/fleet/nodes
- GET /v1/fleet/topology
- GET /v1/fleet/route
- GET /v1/fleet/capabilities
- GET /v1/fleet/registry/hygiene
- GET /v1/filesystem

OpenAI-compatible model/agent registry:
- GET /v1/models

Primary task/model interface:
- POST /v1/responses

Compatibility interface:
- POST /v1/chat/completions

Agent task interface:
- POST /v1/agents/tasks
- GET /v1/agents/status/{task_id}
- GET /v1/agents/artifacts/{task_id}
- POST /v1/agents/cancel/{task_id}

Future optional interfaces:
- POST /v1/embeddings
- POST /v1/images/generations
- POST /v1/audio/transcriptions
- POST /v1/audio/speech

Required docs:
- docs/superfactory/OPENAI_COMPATIBLE_FABRIC_API.md
- docs/superfactory/FABRIC_API_ENDPOINTS.md
- docs/superfactory/FABRIC_SERVER_CONNECTIVITY.md
- docs/superfactory/FABRIC_NODE_REGISTRY.md
- docs/superfactory/FABRIC_ROUTING_POLICY.md
- docs/superfactory/FABRIC_AGENT_PROTOCOL.md
- docs/superfactory/FABRIC_HEALTH_AND_DISCOVERY.md
- docs/superfactory/FABRIC_ERROR_MODEL.md
- docs/superfactory/FABRIC_OBSERVABILITY_HEADERS.md
- docs/superfactory/FABRIC_API_MIGRATION_PLAN.md
- docs/superfactory/TASKS.md

Implementation, if safe and small:
- ops/factory_control.py
- ops/agent_host.py
- ops/kolibri-dispatch
- ops/mesh_control_bridge.py
- backend/adapter.py
- backend/providers.py
- tests/test_factory_runtime.py
- tests/test_agent_host*
- new tests if needed

Forbidden in this task:
- frontend/PWA changes;
- billing changes;
- FormulaLM training implementation;
- Telegram UX redesign;
- PR #46 split;
- qjns/uiap cleanup;
- server credential changes;
- model downloads;
- local LLM installation;
- image generation setup;
- destructive git commands;
- printing secrets.

Every node record must include:
{
  "id": "...",
  "name": "...",
  "type": "command|execution|hybrid|model|tool|gateway",
  "status": "online|degraded|offline|unreachable|unknown",
  "role": "...",
  "capabilities": [],
  "api_base": "...",
  "health_url": "...",
  "last_seen": "...",
  "disk_free_gb": null,
  "ram_available_mb": null,
  "cpu_count": null,
  "gpu": [],
  "can_command": true,
  "can_execute": true,
  "can_host_control_plane": false,
  "can_run_llm": false,
  "can_run_image_generation": false,
  "can_run_formulalm": false,
  "can_run_tests": true,
  "can_access_github": "yes|no|unknown",
  "blockers": [],
  "fallback_nodes": [],
  "last_error": null
}

Error model:
No raw “server unavailable” final answer.
Use structured errors:
{
  "status": "blocked",
  "error_code": "node_unreachable|ssh_timeout|api_unreachable|disk_full|github_auth_failed|control_plane_unreachable|unsupported_capability|no_healthy_route",
  "node": "...",
  "reason": "...",
  "fallback_nodes": [],
  "repair_task": "...",
  "can_continue": true
}

Routing rules:
1. Prefer healthy nodes with matching capability.
2. Avoid nodes with disk_free_gb == 0.
3. Avoid qjns/uiap until repaired unless task is diagnostic.
4. Prefer primary-candidate/main/Home/Primorye for control/implementation.
5. If target unavailable, route to fallback and create repair task.
6. If no route exists, return structured blocked with exact reason.
7. Never hide unavailable nodes; list them with reason.
8. Never require direct SSH from Mac if Control Plane/API path exists.

OpenAI-compatible standard:
All internal agents/services must be wrapped behind:
- /v1/responses
- /v1/chat/completions
- /v1/models

Adapters to define:
- ControlPlaneAdapter
- AgentHostAdapter
- MimoAgentAdapter
- ApiAgentAdapter
- LocalLLMAdapter
- FormulaLMAdapter
- ImageServiceAdapter
- OCRVisionAdapter
- ReviewAgentAdapter
- QAAgentAdapter
- GitHubAgentAdapter
- TelegramCommandAdapter
- CLICommandAdapter

Observability headers:
- X-Kolibri-Task-Id
- X-Kolibri-Trace-Id
- X-Kolibri-Source
- X-Kolibri-Command-Node
- X-Kolibri-Agent-Role
- X-Kolibri-Autopilot-Level
- X-Kolibri-Data-Sensitivity

Tests to add/propose:
- fleet nodes endpoint returns all known nodes.
- degraded nodes are included, not hidden.
- qjns/uiap disk 0.0 creates degraded status.
- unreachable node returns structured blocked with fallback.
- /v1/models lists agent/model services.
- route selection avoids degraded disk-full nodes.
- command from Mac and command from Primorye produce same envelope.
- no secrets appear in node/model responses.
- unsupported capability returns structured blocked.

Acceptance:
- Unified OpenAI-compatible Fabric API is declared as first P0 foundation.
- Every command node uses same task shape.
- Every server/agent/model/service has registry/adapter plan.
- Agent can answer how many servers exist and their status.
- Unavailable servers are not hidden and not dead-end failures.
- Structured error/fallback model exists.
- Routing policy exists.
- /v1/models, /v1/responses, /v1/chat/completions, /v1/fleet/nodes and /v1/agents/tasks roles are defined.
- No unrelated product features are changed.
- No secrets are printed.
- Next exact implementation task is written.
```

---

# 4. P0 Command Fabric HA and Any-Node Control

```text
TASK: P0_COMMAND_FABRIC_HA_AND_ANY_NODE_CONTROL

Goal:
Update Kolibri Factory architecture so Mac is not the only command point.
The factory must support command/control from Mac, Primorye server, Home server, main, primary-candidate, Telegram, phone, GitHub and any trusted computer/server.

Important owner correction:
Mac is only one thin command client.
Primorye and Home are also main command/control servers.
Primorye can both command and execute work because it has server resources.
Home is a reserve command/control node.
If Mac is unavailable, the owner must be able to log into any trusted server or use Telegram/phone and continue issuing tasks.

Do not implement product code in this task.
This is architecture, policy, runbook and task-envelope design only.

Read first:
- docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/GLOBAL_DIGEST_FOR_CHATGPT.md
- ops/factory_control.py
- ops/agent_host.py
- ops/kolibri-dispatch
- ops/telegram_gateway.py
- ops/systemd/
- README.md

Create/update:
- docs/superfactory/00_GOAL.md
- docs/superfactory/COMMAND_FABRIC_HA.md
- docs/superfactory/COMMAND_NODES.md
- docs/superfactory/CONTROL_PLANE_HA.md
- docs/superfactory/FAILOVER_RUNBOOK.md
- docs/superfactory/ANY_SERVER_COMMAND_MODE.md
- docs/superfactory/TELEGRAM_COMMAND_GATEWAY.md
- docs/superfactory/OWNER_ACCESS_RECOVERY.md
- docs/superfactory/ARTIFACT_REPLICATION_POLICY.md
- docs/superfactory/NODE_FAILURE_POLICY.md
- docs/superfactory/PAYMENT_OR_PROVIDER_FAILURE_POLICY.md
- docs/superfactory/TASKS.md

Architecture requirements:
1. Define command node as any trusted device/server that can:
   - create task envelope;
   - submit task to Control Plane;
   - query task status;
   - collect artifacts;
   - update GitHub/PR;
   - report to owner.

Command nodes:
- Mac
- Primorye
- Home
- main
- primary-candidate
- Telegram gateway
- phone
- trusted laptop/desktop
- GitHub emergency channel

2. Define execution node as server/agent that can:
- implement code;
- run tests;
- run local LLM;
- run FormulaLM;
- run image generation;
- run QA/review;
- run MIMO/API agents;
- return artifacts.

3. For every command node define:
- can_command
- can_execute
- can_be_control_leader
- can_be_standby
- allowed actions
- forbidden actions
- healthcheck
- failover priority

4. Primorye role:
- primary or high-priority command/control server;
- allowed to execute heavy tasks if resources available;
- allowed to dispatch sub-tasks to other agents;
- should have Control Plane/Agent Host capability;
- should take over if Mac is gone.

5. Home role:
- reserve command/control server;
- emergency owner access point;
- standby Control Plane candidate;
- artifact backup candidate;
- safe fallback if Primorye/main/primary-candidate unavailable.

6. HA Control Plane:
- active leader;
- standby nodes;
- failover conditions;
- lease expiry;
- idempotency keys;
- duplicate task prevention;
- split-brain prevention;
- task status replication;
- artifact path replication.

7. Any-server command mode:
Owner must be able to SSH into any trusted server and run:
- kolibri task submit <envelope.json>
- kolibri task status <task_id>
- kolibri nodes
- kolibri artifacts <task_id>
- kolibri failover status
- kolibri command-node register
- kolibri command-node health

8. Telegram/phone mode:
Owner must be able to send task through Telegram:
- /task
- /status
- /nodes
- /artifact
- /approve
- /stop
- /failover

9. GitHub emergency mode:
If Control Plane is unavailable, GitHub can be emergency task ledger:
- issue label: kolibri-task
- branch contains task_id
- PR body contains task envelope
- CI/artifacts capture result
- later Control Plane imports the task

10. Failure scenarios:
- Mac lost/unavailable
- Primorye down
- Home down
- main down
- primary-candidate down
- Telegram unavailable
- GitHub unavailable
- Control Plane down
- Redis down
- server unpaid/suspended
- node disk full
- node GitHub auth broken
- split brain / two leaders
- artifact server gone
- owner only has phone

Safety:
No command node may:
- print secrets;
- push to main;
- force push;
- bypass CI;
- delete data without backup/approval;
- execute destructive task without explicit policy;
- move money automatically;
- abuse free resources or violate provider terms.

Acceptance:
- New goal explicitly says Mac is not the only command point.
- Primorye and Home are defined as command/control servers.
- Any trusted server can become command node.
- Phone/Telegram command path is defined.
- GitHub emergency mode is defined.
- Failover scenarios are documented.
- No product code changed.
- Next exact implementation tasks are created.
```

---

# 5. P0 OpenAI-Compatible Fabric API Standard

```text
TASK: P0_KOLIBRI_OPENAI_COMPATIBLE_FABRIC_API_STANDARD

Goal:
Add a mandatory OpenAI-compatible API standard for the entire Kolibri Factory.

Owner correction:
All servers, agents, local LLMs, MIMO agents, API agents, FormulaLM components, image/OCR services, review agents, QA agents and command nodes must communicate through one OpenAI-like API contract.

This does NOT mean using external OpenAI services.
This means Kolibri internally standardizes on an OpenAI-compatible protocol so every component can be swapped, routed, observed, tested and composed.

Important:
This task is documentation and contract design only.
Do not implement product code yet.
Do not change backend routes yet.
Do not modify secrets.
Do not call external providers.
Do not install models.
Do not run heavy tests.

Read first:
- docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/GLOBAL_DIGEST_FOR_CHATGPT.md
- backend/providers.py
- backend/adapter.py
- backend/pipeline.py
- ops/agent_host.py
- ops/factory_control.py
- ops/kolibri-dispatch
- ops/telegram_gateway.py
- ops/mesh_control_bridge.py
- README.md

Create/update:
- docs/superfactory/OPENAI_COMPATIBLE_FABRIC_API.md
- docs/superfactory/FABRIC_API_ENDPOINTS.md
- docs/superfactory/FABRIC_AGENT_PROTOCOL.md
- docs/superfactory/FABRIC_MODEL_REGISTRY_API.md
- docs/superfactory/FABRIC_TOOL_CALLING_STANDARD.md
- docs/superfactory/FABRIC_STREAMING_STANDARD.md
- docs/superfactory/FABRIC_STRUCTURED_OUTPUTS_STANDARD.md
- docs/superfactory/FABRIC_OBSERVABILITY_HEADERS.md
- docs/superfactory/FABRIC_PROVIDER_ADAPTERS.md
- docs/superfactory/FABRIC_API_MIGRATION_PLAN.md
- docs/superfactory/TASKS.md

Core principle:
Every Kolibri component must either expose or consume one of these standard APIs:
- /v1/models
- /v1/responses
- /v1/chat/completions
- /v1/embeddings
- /v1/images/generations
- /v1/audio/transcriptions
- /v1/audio/speech
- /v1/agents/tasks
- /v1/agents/status
- /v1/agents/artifacts

Primary interface:
Use `/v1/responses` as the future primary Kolibri agent/model interface.

Compatibility interface:
Keep `/v1/chat/completions` for OpenAI-compatible SDKs, local LLM runtimes, MIMO/API agents, legacy tools and existing integrations.

Model registry:
Every model/agent/service must be listed through `/v1/models`.

Each model record must include:
{
  "id": "kolibri-text-qwen-local",
  "object": "model",
  "owned_by": "kolibri",
  "capabilities": [
    "chat",
    "responses",
    "tools",
    "structured_outputs",
    "vision",
    "embeddings",
    "image_generation",
    "code",
    "review",
    "qa"
  ],
  "server_node": "...",
  "agent_type": "local_llm|mimo|api_agent|formula_lm|image_service|ocr_service|review_agent|qa_agent",
  "status": "available|busy|degraded|offline",
  "context_window": "...",
  "supports_streaming": true,
  "supports_tools": true,
  "supports_json_schema": true,
  "cost_policy": "local|free_authorized|paid_approval_required",
  "data_policy": "public|internal|sensitive_allowed|sensitive_forbidden"
}

Required request metadata:
{
  "task_id": "...",
  "trace_id": "...",
  "owner": "Vladislav",
  "source": "mac|primorye|home|telegram|github|control_plane|agent_host",
  "command_node": "...",
  "target_pool": ["..."],
  "agent_role": "...",
  "autopilot_level": "A0|A1|A2|A3|A4|A5",
  "budget_policy": "...",
  "data_sensitivity": "public|internal|sensitive|secret",
  "required_outputs": [],
  "artifact_policy": "...",
  "write_scope": [],
  "constraints": {}
}

Required response metadata:
{
  "id": "...",
  "object": "response|chat.completion|agent.task.result",
  "task_id": "...",
  "trace_id": "...",
  "model": "...",
  "agent_id": "...",
  "server_node": "...",
  "status": "completed|blocked|failed|partial|running",
  "output": "...",
  "tool_calls": [],
  "artifacts": [],
  "required_artifacts_present": [],
  "required_artifacts_missing": [],
  "tests_run": [],
  "blocked_reason": "...",
  "failure_reason": "...",
  "next_recommended_task": "..."
}

Agent protocol:
Every agent must be wrapped as an OpenAI-compatible model or assistant-like endpoint.

Examples:
- Codex remote agent: kolibri-agent-codex-implementation
- MIMO remote agent: kolibri-agent-mimo-free
- API-based free authorized agent: kolibri-agent-api-free-<provider>
- Local LLM on server: kolibri-local-llm-<node>-<model>
- FormulaLM: kolibri-formulalm-router / verifier / adapter-generator
- Image generation service: kolibri-image-local
- OCR/Vision service: kolibri-vision-ocr-local
- QA/review agent: kolibri-agent-review / kolibri-agent-qa

Routing rule:
Agents must not call each other through custom private formats if an OpenAI-compatible endpoint exists.

Tool calling standard:
All tools must be exposed through JSON Schema-compatible tool definitions.

Structured outputs:
If a task requires JSON, use JSON Schema / structured output contract.
No free-form JSON-like text for critical results.

Streaming:
Streaming must use OpenAI-like SSE chunks where possible and preserve task_id/trace_id/model/agent_id/final status.

Security:
Never send secrets through model prompts.
Never log tokens.
Never expose API keys in traces.
Sensitive data must require explicit data_policy.
External/free API agents must not receive sensitive/private customer data unless explicitly approved.

Provider adapters:
- LocalLLMAdapter
- MimoAgentAdapter
- ApiAgentAdapter
- FormulaLMAdapter
- ImageServiceAdapter
- OCRVisionAdapter
- ReviewAgentAdapter
- QAAgentAdapter
- ToolServerAdapter
- GitHubAgentAdapter
- ControlPlaneAdapter

Migration plan:
Phase 0: document standard.
Phase 1: inventory existing routes/adapters.
Phase 2: add non-breaking /v1/models inventory endpoint.
Phase 3: add /v1/responses internal router.
Phase 4: add /v1/chat/completions compatibility shim.
Phase 5: wrap Agent Host tasks as OpenAI-compatible agent models.
Phase 6: wrap MIMO/API agents.
Phase 7: wrap local LLM/image/OCR services.
Phase 8: make Telegram/PWA/CLI submit through same fabric API.
Phase 9: add tests/evals.
Phase 10: deprecate private formats after compatibility is proven.

Acceptance:
- OpenAI-compatible API is declared as single internal language of Kolibri Factory.
- Every server/agent/model/service type has adapter plan.
- /v1/responses and /v1/chat/completions roles are defined.
- /v1/models registry schema is defined.
- Tool calling, structured outputs, streaming and metadata propagation are defined.
- Mac, Primorye, Home, Telegram, GitHub and servers all use same task/API shape.
- No product code changed.
- No secrets printed.
- Next exact implementation task written.
```

---

# 6. Dispatch P0 Runner Hardening to Remote Factory

```text
TASK: DISPATCH_P0_RUNNER_HARDENING_TO_REMOTE_FACTORY

Role:
Mac thin-client dispatcher.

Goal:
Do not implement locally.
Dispatch P0 Agent Host runner hardening to remote Kolibri Factory agents.

Primary remote task:
P0_AGENT_HOST_GENERIC_RUNNER_CONTRACT_HARDENING_2026_06_30

Preferred execution:
- primary-candidate
- main
- Home
- Primorye
- any healthy implementation-capable node
- MIMO remote agents if available
- API-based authorized implementation/review agents if available

Avoid until repaired:
- qjns if disk/GitHub auth still broken
- uiap if disk free is still 0.0 GB
- any node with disk 0.0 GB
- any node without GitHub clone/fetch access unless task is diagnostic only

Mac responsibilities:
1. Read project context.
2. Prepare remote task envelope.
3. Submit envelope through Control Plane or SSH/API relay to control node.
4. Record task_id.
5. Watch status.
6. Collect result artifact.
7. Summarize for owner.
8. Do not implement product code locally.

Create local dispatcher docs:
- docs/agent/dispatcher/QUEUE.md
- docs/agent/dispatcher/DISPATCH_LOG.md
- docs/agent/dispatcher/REMOTE_AGENTS.md
- docs/agent/dispatcher/REMOTE_RESULTS.md
- docs/agent/dispatcher/FACTORY_STATUS.md

Remote task objective:
Harden `ops/agent_host.py` generic runner so tasks cannot falsely report success, ignore required outputs, violate no-push/read-only/write_scope constraints, or hide blocked/failed states.

Remote task must:
- create a clean server branch from origin/main;
- use branch `p0/agent-host-runner-contract-hardening-2026-06-30`;
- implement only runner contract hardening;
- add tests;
- create docs;
- push task branch;
- open/update PR if allowed;
- run server/CI validation;
- return human-readable result.

Allowed remote files:
- ops/agent_host.py
- ops/factory_control.py only if result schema requires it
- ops/kolibri-dispatch only if status/collect output needs alignment
- tests/test_agent_host*
- tests/test_factory_runtime.py
- docs/agent/AGENT_RUNNER_CONTRACT.md
- docs/agent/runs/2026-06-30-p0-agent-host-runner-contract-hardening/

Forbidden remote files:
- frontend
- billing
- FormulaLM implementation
- Telegram UX
- qjns/uiap repair
- server credentials
- mesh URL extraction
- organism API deduplication
- PR #46 split
- model gateway

Remote acceptance:
- runner refuses push when forbidden;
- runner refuses completed if required artifacts missing;
- runner enforces write_scope;
- runner blocks/fails product code changes in read-only/docs-only mode;
- unsupported task kind returns structured blocked;
- result schema includes required fields;
- tests cover new behavior;
- branch/PR/result artifact returned.

Mac final output:
- submitted task_id;
- remote node/agent pool;
- status;
- lease owner if known;
- branch;
- PR URL if created;
- result artifact path;
- summary;
- blockers.
```

---

# 7. P0 Agent Host Generic Runner Contract Hardening

```text
TASK: P0_AGENT_HOST_GENERIC_RUNNER_CONTRACT_HARDENING_2026_06_30

Mode:
Remote supervised P0 development task.

Goal:
Harden Kolibri Agent Host generic runner so factory tasks cannot falsely report success, write artifacts to wrong paths, ignore required outputs, violate read-only/no-push/write_scope constraints, or hide blocked/failed states.

Context:
Read first:
- docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/GLOBAL_DIGEST_FOR_CHATGPT.md
- ops/agent_host.py
- ops/factory_control.py
- ops/kolibri-dispatch
- tests/test_agent_host*
- tests/test_factory_runtime.py
- .github/workflows/ci.yml

Branch:
Use branch:
p0/agent-host-runner-contract-hardening-2026-06-30

Do not work directly in dirty runtime repos.
Do not mix this with PR #46.

Allowed files:
- ops/agent_host.py
- ops/factory_control.py only if task/result schema requires it
- ops/kolibri-dispatch only if status/collect output needs alignment
- tests/test_agent_host*
- tests/test_factory_runtime.py
- docs/agent/AGENT_RUNNER_CONTRACT.md
- docs/agent/runs/2026-06-30-p0-agent-host-runner-contract-hardening/

Forbidden:
- frontend changes
- billing changes
- FormulaLM changes
- Telegram UX changes
- qjns/uiap disk cleanup
- server GitHub credential repair
- mesh URL extraction
- organism API deduplication
- PR #46 split
- model gateway
- sovereign model factory
- destructive git commands
- secret printing

Required behavior:
1. No-push enforcement.
If envelope contains git_push_forbidden/no_push/read_only, runner must not push under any circumstance.

2. Read-only enforcement.
If read_only is set, product code changes are forbidden unless explicitly allowed by write_scope.

3. Product-code modification guard.
If product_code_modification_forbidden is set, changes outside allowed docs/artifact paths fail/block.

4. Documentation/artifact-only mode.
If documentation_artifacts_only is set, only docs/artifact/write_scope paths are allowed.

5. write_scope enforcement.
Any write outside write_scope makes task blocked/failed.

6. required_outputs / required_artifacts verification.
Every required file must exist before success.
Missing files must be listed and status must not be completed.

7. Unsupported task kind/capability.
Return structured blocked result.
Do not fake success.
Do not start random fallback implementation.

8. Result schema:
{
  "task_id": "...",
  "status": "completed|blocked|failed",
  "changed_files": [],
  "artifact_dir": "...",
  "required_artifacts_present": [],
  "required_artifacts_missing": [],
  "write_scope": [],
  "write_scope_violations": [],
  "read_only": true/false,
  "product_code_modification_forbidden": true/false,
  "product_code_changed": true/false,
  "push_attempted": true/false,
  "push_blocked": true/false,
  "blocked_reason": "...",
  "failure_reason": "...",
  "tests_run": [],
  "next_recommended_task": "..."
}

Status rules:
Runner must never return completed if:
- required files missing;
- write_scope violated;
- forbidden product code changed;
- push was forbidden but attempted;
- task kind/capability unsupported;
- artifact directory missing;
- result.json cannot be written.

Documentation:
Create:
docs/agent/AGENT_RUNNER_CONTRACT.md

Tests required:
- no-push enforcement;
- read-only enforcement;
- product-code change forbidden;
- docs-only output allowed;
- write_scope enforcement;
- required artifact verification;
- missing artifact returns blocked/failed;
- unsupported task kind returns structured blocked;
- previous P0 integration audit artifact path drift case;
- result schema contains required fields.

Test classification:
Classify every test as:
- passed_local_mac
- failed_local_mac
- unavailable_on_mac
- deferred_to_server
- deferred_to_ci
- blocked_missing_dependency
- blocked_missing_secret_or_env
- blocked_network_or_control_plane
- not_run_with_reason

Suggested commands:
- python -m pytest tests/test_agent_host* -q
- python -m pytest tests/test_factory_runtime.py -q
- python -m pytest -q

Required artifacts:
- docs/agent/runs/2026-06-30-p0-agent-host-runner-contract-hardening/PLAN.md
- docs/agent/runs/2026-06-30-p0-agent-host-runner-contract-hardening/ACTIONS.md
- docs/agent/runs/2026-06-30-p0-agent-host-runner-contract-hardening/TESTS.md
- docs/agent/runs/2026-06-30-p0-agent-host-runner-contract-hardening/RESULT.md
- docs/agent/runs/2026-06-30-p0-agent-host-runner-contract-hardening/NEXT.md

Final response:
- status;
- branch name;
- files changed;
- tests run;
- test classification;
- exact behavior implemented;
- blocked items;
- PR ready yes/no;
- next recommended task.
```

---

# 8. P0 GitHub Operating System for Kolibri Factory

```text
TASK: P0_GITHUB_OPERATING_SYSTEM_FOR_KOLIBRI_FACTORY

Role:
GitHub Curator / Repository Operator / Project Maintainer.

Repository:
https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform

Goal:
Полностью навести порядок в приватном GitHub-репозитории Kolibri AI Platform и превратить GitHub в постоянно актуальный центр управления проектом, а не просто место для pull requests.

GitHub must become:
- source of truth for branches, PRs, issues, CI, releases and project state;
- owner-visible project dashboard;
- task ledger for agents;
- roadmap and backlog;
- PR quality gate;
- artifact/status index;
- emergency task ledger if Control Plane is unavailable.

Important:
This is a GitHub governance subproject.
Do not randomly modify product code.
Do not merge PRs automatically.
Do not delete branches without archive plan and owner approval.
Do not close issues/PRs without explanation.
Do not print secrets, tokens, keys or env values.
Do not force push.
Do not push to main.
Do not bypass CI.

Read first:
- README.md
- .github/workflows/ci.yml
- docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/GLOBAL_DIGEST_FOR_CHATGPT.md
- docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/ALL_BRANCHES_GLOBAL_MATRIX.md if present
- docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/NEXT_DEVELOPMENT_TASKS.md if present
- docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/RISK_REGISTER.md if present
- existing open PRs
- existing issues
- existing labels
- existing milestones
- existing GitHub Projects if any
- branch protection / rulesets if accessible

Create branch:
p0/github-operating-system-2026-06-30

Create output directory:
docs/github/operating-system/2026-06-30/

Create files:
- EXECUTIVE_SUMMARY.md
- GITHUB_CURRENT_STATE.md
- REPOSITORY_GOVERNANCE.md
- LABEL_TAXONOMY.md
- ISSUE_TEMPLATES_PLAN.md
- PR_TEMPLATE.md
- BRANCH_POLICY.md
- PR_REVIEW_POLICY.md
- CI_STATUS_POLICY.md
- PROJECT_BOARD_DESIGN.md
- MILESTONES_AND_ROADMAP.md
- STALE_BRANCH_AND_PR_POLICY.md
- RELEASE_POLICY.md
- SECURITY_AND_SECRETS_POLICY.md
- AGENT_GITHUB_CURATOR_RUNBOOK.md
- DAILY_GITHUB_STATUS_TEMPLATE.md
- WEEKLY_REPO_AUDIT_TEMPLATE.md
- GITHUB_AUTOMATION_PLAN.md
- ACTIONS_TO_APPLY.md
- BLOCKED_ADMIN_ACTIONS.md
- NEXT_TASKS.md

Inventory:
- repo owner/name/private status;
- default branch;
- branch protections/rulesets;
- open PRs;
- draft PRs;
- blocked PRs;
- stale PRs;
- recent closed/merged PRs;
- open issues;
- labels;
- milestones;
- GitHub Projects;
- workflow files;
- recent CI runs;
- failing checks;
- branch list;
- stale branches;
- high-risk branches;
- huge PRs;
- CODEOWNERS;
- issue templates;
- PR template;
- SECURITY.md;
- CONTRIBUTING.md;
- RELEASE.md / CHANGELOG.

Special focus:
- PR #46 must be classified as split-required.
- PRs mixing PWA/billing/FormulaLM/runner/Telegram/backend/DevOps/credentials must be high risk.
- Dirty runtime repos on main/primary-candidate must be tracked as GitHub issues/tasks.
- Server GitHub auth blocker must be tracked.
- uiap/qjns disk blockers must be tracked.
- Agent Host runner hardening must be P0 issue/PR/task.

Label taxonomy:
Priority:
- P0, P1, P2, P3

Type:
- type:bug
- type:feature
- type:docs
- type:infra
- type:security
- type:test
- type:refactor
- type:research
- type:agent-task

Subsystem:
- area:frontend
- area:backend
- area:control-plane
- area:agent-host
- area:telegram
- area:formula-lm
- area:estimates
- area:billing
- area:github-ci
- area:devops
- area:fleet
- area:model-factory
- area:docs

Status:
- status:ready
- status:blocked
- status:needs-review
- status:needs-split
- status:waiting-ci
- status:in-progress
- status:stale
- status:owner-approval

Risk:
- risk:low
- risk:medium
- risk:high
- risk:dangerous

Agent:
- agent:codex
- agent:mimo
- agent:api
- agent:review
- agent:qa
- agent:human

Required P0 issues:
1. P0 Unified Fabric API and Server Connectivity
2. P0 Agent Host Generic Runner Contract Hardening
3. P0 GitHub Operating System and Repository Governance
4. P0 Command Fabric HA and Any-Node Control
5. P0 Fleet Resource Inventory and Reachability
6. P0 Repair uiap/qjns Disk and Server GitHub Auth
7. P0 Preserve Dirty Runtime Diffs from main and primary-candidate
8. P0 Split PR #46 into safe PRs

PR template must require:
- Summary
- Scope
- Explicitly not included
- Linked issue/task_id
- Files changed by subsystem
- Tests run
- Tests unavailable and why
- CI status
- Risk level
- Rollback plan
- Screenshots/artifacts if UI
- Migration notes if backend/infra
- Secrets touched yes/no
- Owner approval required yes/no
- Agent final report link

GitHub Project:
Kolibri Factory OS

Views:
- P0 Command Center
- Active PRs
- Blocked
- Server/Fleet
- GitHub/CI
- Product
- Model Factory
- FormulaLM
- Business
- Done

Fields:
- Priority
- Area
- Status
- Risk
- Owner/Agent
- Target Node
- Autopilot Level
- Due/Review Date
- Linked PR
- Linked Artifact
- Blocker
- Next Action

Continuous GitHub Curator:
- Daily: check open PRs, failed CI, blocked issues, stale branches, P0 status.
- After every agent task: update issue/PR/status/artifact links.
- Weekly: stale branch review, milestone review, roadmap update.
- Before merge: scope/test/risk/rollback check.
- After merge: close linked issue, update changelog/status, archive branch if safe.
- Always: keep README/docs/project board current.

Final response:
- status;
- branch name;
- GitHub access status;
- files created/updated;
- labels created/proposed;
- issues created/proposed;
- project board created/proposed;
- PR template status;
- branch protection/ruleset recommendation;
- top 10 repo problems;
- top 10 next actions;
- blocked admin actions;
- exact PR title/body for this governance PR.

Acceptance:
- GitHub has clear operating model, not just PRs.
- Every P0/P1 work item has issue or proposed issue.
- PR #46 has split plan tracking.
- Labels/milestones/projects are defined.
- PR/issue templates exist or are proposed.
- Branch policy and review policy exist.
- Daily GitHub curator runbook exists.
- Agent can keep GitHub current continuously after this.
```

---

# 9. P0 Public Site and Backend Vertical Audit

```text
TASK: P0_PUBLIC_SITE_AND_BACKEND_VERTICAL_AUDIT

Goal:
Audit https://kolibriai.ru/ and the current Kolibri frontend/backend codebase to produce a concrete improvement plan for design, UX, SEO and backend API.

Important:
Do not implement redesign yet.
Do not modify product code in this task unless explicitly approved.
Create audit artifacts and implementation-ready plan.

Live site:
https://kolibriai.ru/

Known public positioning:
Kolibri is currently indexed as an AI assistant for tasks, documents and code.
The project itself is larger: distributed AI/platform factory with backend/API, frontend/PWA, Telegram, Control Plane, Agent Host, mesh/runtime workers, deterministic estimates, documents/PDF, billing scaffold, LLM provider stack and server automation.

Read first:
- docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/GLOBAL_DIGEST_FOR_CHATGPT.md
- frontend/
- frontend/package.json
- backend/
- backend/providers.py
- backend/adapter.py
- backend/pipeline.py
- backend/estimate_engine.py
- backend/document_engine.py
- backend/pdf_engine.py
- ops/factory_control.py
- ops/agent_host.py
- ops/telegram_gateway.py
- .github/workflows/ci.yml

Create output directory:
docs/product/public-site-audit/2026-06-30-kolibriai-vertical-audit/

Create files:
1. EXECUTIVE_SUMMARY.md
2. LIVE_SITE_REVIEW.md
3. DESIGN_UX_AUDIT.md
4. SEO_METADATA_AUDIT.md
5. FRONTEND_ARCHITECTURE_AUDIT.md
6. BACKEND_API_AUDIT.md
7. FRONTEND_BACKEND_ROUTE_MATRIX.md
8. VERTICAL_POSITIONING.md
9. LANDING_PAGE_COPY_V1.md
10. BACKEND_FABRIC_API_PLAN.md
11. DEMO_MODE_PLAN.md
12. IMPLEMENTATION_ROADMAP.md
13. RISK_REGISTER.md
14. NEXT_TASK_PROMPTS.md

Audit live site:
- desktop screenshot
- mobile screenshot
- title
- description
- H1/H2
- visible CTA
- visible product promise
- loading performance if Lighthouse available
- OpenGraph/Twitter meta
- robots/sitemap presence if accessible
- whether content is server-rendered/indexable
- whether page explains:
  - tasks
  - documents
  - estimates
  - code
  - agents
  - server/private AI factory
  - Telegram/Web UI
  - security/privacy

Audit design:
- first screen clarity
- visual hierarchy
- CTA clarity
- typography
- color system
- spacing
- mobile layout
- trust signals
- product screenshots
- demo flow
- artifact/result visibility

Audit frontend:
- framework
- routes
- API calls
- WebSocket/SSE calls
- document upload flows
- estimate flows
- factory status flows
- provider/model flows
- hardcoded URLs
- missing env config
- component structure
- unused components
- build command
- test command

Audit backend:
- actual routes
- expected frontend routes
- missing routes
- duplicate routes
- provider stack
- estimate/document/PDF endpoints
- task/status/artifact support
- auth/rate limit
- error model
- streaming support
- OpenAI-compatible endpoints
- Fabric API readiness

Create route matrix:
frontend_call | method | backend_route_exists | schema_match | risk | recommended_action

Pay special attention to:
- /api/chat
- /ws/chat
- /api/providers
- /api/factory/status
- /cluster/status
- /api/knowledge
- /rag/search
- document upload/download
- estimate endpoints
- /v1/models
- /v1/responses
- /v1/chat/completions
- /v1/agents/tasks
- /v1/agents/status
- /v1/agents/artifacts

Vertical positioning:
Propose new positioning:
"Kolibri AI — суверенная AI-фабрика для задач, документов, смет и кода."

Write:
- new hero title
- subtitle
- 3 CTA variants
- 6 feature cards
- 3 demo scenarios
- security/private infrastructure block
- Telegram/Web/Server agents block
- pricing/contact block
- footer copy

Backend plan:
Define P0 API improvements:
- /v1/health
- /v1/models
- /v1/responses
- /v1/chat/completions
- /v1/agents/tasks
- /v1/agents/status/{task_id}
- /v1/agents/artifacts/{task_id}
- /v1/factory/status
- /v1/fleet/nodes
- /v1/documents/analyze
- /v1/estimates/draft
- /v1/estimates/calculate

Demo mode:
Design safe public demo:
- no arbitrary shell/tools
- no secrets
- no private server state
- rate limits
- max file size
- max task time
- allowed scenarios:
  1. summarize task
  2. analyze document
  3. draft estimate
  4. code review sample
  5. agent plan demo

Roadmap:
Split implementation into PRs:
PR 1: SEO/meta/landing copy quick win
PR 2: route matrix + backend compatibility shims
PR 3: demo mode API
PR 4: landing redesign components
PR 5: task/artifact UX
PR 6: Fabric API MVP

Do not mix:
- billing
- FormulaLM training
- server credentials
- runner hardening
- Telegram gateway refactor
- PR #46 split

Acceptance:
- audit docs created;
- exact design changes proposed;
- exact backend route gaps listed;
- first safe PR identified;
- next implementation prompt created.
```

---

# 10. P0 Superfactory Documentation Package

```text
TASK: P0_CREATE_KOLIBRI_SUPERFACTORY_DOCUMENTATION_PACKAGE

Goal:
Create the full Kolibri Superfactory operating manual.

Scope:
Documentation only.
Do not implement product code.

Read first:
- docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/GLOBAL_DIGEST_FOR_CHATGPT.md
- docs/agent/AGENT_RUNNER_CONTRACT.md if it exists
- README.md
- ops/agent_host.py
- ops/factory_control.py

Create:
- docs/superfactory/00_README.md
- docs/superfactory/00_GOAL.md
- docs/superfactory/01_VISION.md
- docs/superfactory/02_OWNER_AUTHORITY.md
- docs/superfactory/03_SAFETY_GATES.md
- docs/superfactory/04_AUTOPILOT_LEVELS.md
- docs/superfactory/05_AGENT_CONTRACT.md
- docs/superfactory/06_GITHUB_ALWAYS_CURRENT.md
- docs/superfactory/07_FLEET_ARCHITECTURE.md
- docs/superfactory/08_AGENT_TEAM_MESH.md
- docs/superfactory/09_SKILL_REGISTRY.md
- docs/superfactory/10_SKILL_INTERNET_DISCOVERY.md
- docs/superfactory/11_SERVER_BOOTSTRAP.md
- docs/superfactory/12_LOCAL_LLM_RING.md
- docs/superfactory/13_MODEL_REGISTRY_AND_FORMULALM.md
- docs/superfactory/14_100K_LOGICAL_AGENTS.md
- docs/superfactory/15_BUSINESS_ENGINE.md
- docs/superfactory/16_FINANCE_POLICY.md
- docs/superfactory/17_PHONE_VIDEO_RELAY_POLICY.md
- docs/superfactory/18_VIDEO_AVATAR_MEETINGS.md
- docs/superfactory/19_OBSERVABILITY_AND_ANTI_DEGRADATION.md
- docs/superfactory/20_ROADMAP.md
- docs/superfactory/TASKS.md

Rules:
- No product code changes.
- No secrets.
- No frontend/billing/FormulaLM implementation.
- No destructive git commands.

Each document must define:
- purpose;
- allowed actions;
- forbidden actions;
- owner approval gates;
- artifacts;
- acceptance criteria;
- next task.

TASKS.md must contain ordered roadmap:
P0 unified fabric API;
P0 command fabric HA;
P0 runner hardening;
P0 GitHub OS;
P0 fleet inventory;
P0 disk/GitHub auth repair;
P0 dirty diff preservation;
P1 skill registry;
P1 team mesh;
P1 anti-degradation;
P1 integration audit;
P1 PR #46 split;
P2 logical agents;
P2 local LLM ring;
P2 sovereign model factory;
P2 business engine;
P3 video avatars;
P3 START autopilot.

Final response:
- status;
- files created;
- risks;
- next task.
```

---

# 11. P0 Fleet Resource Inventory and Reachability

```text
TASK: P0_FLEET_RESOURCE_INVENTORY_AND_REACHABILITY

Goal:
Use the whole Kolibri server network as a coordinated resource pool.

Context:
Control Plane sees 20 node cards.
Direct SSH from Mac reaches only `main` and `primary-candidate`.
`uiap` and `qjns` report 0.0 GB disk free.

Scope:
Read-only inventory.
Do not fix servers in this task.
Do not install packages.
Do not delete files.
Do not print secrets.

Create:
- docs/superfactory/FLEET_RESOURCE_INVENTORY.md
- docs/superfactory/SERVER_REACHABILITY_MAP.md
- docs/superfactory/SERVER_ROLE_MAP.md
- docs/superfactory/SERVER_HEALTH_RISK_REGISTER.md
- docs/superfactory/FLEET_NEXT_TASKS.md

For every server/node:
- node name;
- hostname;
- role;
- Control Plane reachable yes/no;
- direct SSH reachable yes/no;
- API reachable yes/no;
- disk free;
- RAM;
- CPU;
- GPU via nvidia-smi if available;
- Docker available yes/no;
- systemd available yes/no;
- Agent Host status;
- GitHub clone/fetch status;
- local LLM suitability;
- FormulaLM suitability;
- image generation suitability;
- max safe concurrent physical workers;
- estimated logical agent capacity;
- blockers.

Classify unreachable:
- DNS
- SSH
- VPN/WireGuard
- firewall
- auth
- Control Plane down
- API down
- unknown

Acceptance:
- all 20 nodes classified;
- qjns/uiap disk issue documented;
- direct SSH routing problem documented;
- API fallback routing documented;
- server role map created;
- repair tasks generated.
```

---

# 12. P0 Repair Degraded Server Readiness

```text
TASK: P0_REPAIR_DEGRADED_SERVER_READINESS

Goal:
Repair degraded server readiness for `uiap`, `qjns`, and server-side GitHub noninteractive clone/fetch.

Scope:
Server recovery only.
No product code changes.
No application feature work.

Targets:
- uiap disk 0.0 GB
- qjns disk 0.0 GB
- qjns clone/auth/network
- server GitHub noninteractive HTTPS/SSH clone/fetch

Hard rules:
- Do not print secrets.
- Do not delete unknown data.
- Before cleanup, produce disk report.
- Before GitHub auth changes, document current auth mode.
- Do not hardcode tokens.
- Prefer approved SSH deploy key, GitHub CLI auth, credential manager or API-first node identity.
- If human secret intervention is needed, produce exact request and stop.

Create:
- docs/superfactory/SERVER_REPAIR_REPORT.md
- docs/superfactory/UIAP_DISK_REPORT.md
- docs/superfactory/QJNS_DISK_REPORT.md
- docs/superfactory/GITHUB_AUTH_SERVER_POLICY.md
- docs/superfactory/QJNS_GITHUB_CLONE_REPORT.md
- docs/superfactory/NODE_RECOVERY_NEXT.md

For each node:
- df -h summary;
- largest safe directories;
- artifact/cache/log sizes;
- cleanup candidates;
- cleanup performed yes/no;
- before/after disk free;
- rollback/safety notes.

For GitHub auth:
- remote URL type HTTPS/SSH;
- gh auth status without token values;
- ssh -T result without private key output;
- git ls-remote result;
- git clone temp dir result;
- error classification:
  - DNS
  - network
  - TLS
  - auth
  - permission
  - repo URL
  - disk
  - unknown

Acceptance:
- qjns disk blocker fixed or exact blocker documented.
- uiap disk blocker fixed or exact blocker documented.
- server git ls-remote works or exact blocker documented.
- no secrets leaked.
```

---

# 13. P0 Preserve Dirty Runtime Diffs

```text
TASK: P0_PRESERVE_DIRTY_RUNTIME_DIFFS_MAIN_PRIMARY_CANDIDATE

Goal:
Safely preserve dirty runtime repo changes from `main` and `primary-candidate` before any cleanup, merge, reset, or deployment.

Scope:
Read-only diff capture + documentation.
Do not modify product code.
Do not reset/clean/stash unless explicitly approved.
Do not push runtime dirty changes directly.

Targets:
- main server runtime repo
- primary-candidate server runtime repo

Create:
- docs/superfactory/DIRTY_RUNTIME_DIFFS_REPORT.md
- docs/superfactory/runtime-diffs/main/
- docs/superfactory/runtime-diffs/primary-candidate/
- docs/superfactory/RUNTIME_DIFF_NEXT_TASKS.md

For each server:
- hostname;
- repo path;
- branch;
- HEAD;
- git status --short --branch;
- git diff --stat;
- git diff --name-status;
- full patch saved to artifact file;
- untracked files list;
- modified files grouped by subsystem;
- risk classification;
- whether changes appear valuable;
- whether changes duplicate an existing branch/PR;
- recommended action:
  - preserve only
  - port to branch
  - discard candidate
  - needs human review
  - unknown

Hard rules:
- No secrets.
- Do not print .env values.
- Do not delete or overwrite server files.
- Do not push dirty runtime changes.

Acceptance:
- full diffs preserved as artifacts;
- no server working tree changed;
- next task identifies how to port useful changes safely.
```

---

# 14. P1 Skill Registry and Internet Discovery

```text
TASK: P1_KOLIBRI_SKILL_REGISTRY_AND_INTERNET_DISCOVERY

Goal:
Create Kolibri Skill Registry and discover useful Codex/agent/devops/AI skills from official docs, GitHub and public sources.

Important:
Discover broadly, install selectively.
Do not blindly install executable internet code on servers.

Scope:
Documentation + registry + quarantine plan.
No unsafe install.
No server-wide install yet.

Create:
- docs/superfactory/09_SKILL_REGISTRY.md
- docs/superfactory/10_SKILL_INTERNET_DISCOVERY.md
- docs/superfactory/SKILL_SECURITY_POLICY.md
- docs/superfactory/SKILL_INSTALLATION_POLICY.md
- docs/superfactory/SKILL_EVAL_PLAN.md
- docs/superfactory/SKILL_DISCOVERY_REPORT.md
- .agents/skills/README.md

Create initial internal skills:
- .agents/skills/kolibri-runner-hardening/SKILL.md
- .agents/skills/kolibri-github-curator/SKILL.md
- .agents/skills/kolibri-ci-doctor/SKILL.md
- .agents/skills/kolibri-fleet-inventory/SKILL.md
- .agents/skills/kolibri-server-recovery/SKILL.md
- .agents/skills/kolibri-pr-splitter/SKILL.md
- .agents/skills/kolibri-formulalm-planner/SKILL.md
- .agents/skills/kolibri-model-factory/SKILL.md
- .agents/skills/kolibri-business-builder/SKILL.md
- .agents/skills/kolibri-finance-reporter/SKILL.md

For every discovered skill/source:
- URL;
- license;
- purpose;
- files;
- has scripts yes/no;
- dependencies;
- security risk;
- relevance to Kolibri;
- decision:
  - reject
  - quarantine
  - adapt
  - approve_dev
  - approve_server
  - approve_all_agents

Lifecycle:
discover -> quarantine -> inspect -> license/security check -> adapt -> register -> test -> approve -> install -> sync -> measure.

Acceptance:
- skill registry exists;
- at least 20 skill candidates cataloged;
- at least 10 Kolibri internal skills drafted;
- no unaudited scripts executed;
- next fleet sync task created.
```

---

# 15. P1 Agent Team Mesh and Human Language Protocol

```text
TASK: P1_AGENT_TEAM_MESH_AND_HUMAN_LANGUAGE_PROTOCOL

Goal:
Make Kolibri agents communicate like a coordinated human team.

Scope:
Documentation + role definitions + message protocol.
No product implementation yet unless explicitly scoped.

Create:
- docs/superfactory/08_AGENT_TEAM_MESH.md
- docs/superfactory/AGENT_ROLES.md
- docs/superfactory/AGENT_COMMUNICATION_PROTOCOL.md
- docs/superfactory/TEAM_LEDGER.md
- docs/superfactory/HANDOFF_PROTOCOL.md
- docs/superfactory/DAILY_STANDUP_FORMAT.md
- .agents/team/README.md
- .agents/roles/

Agent roles:
- Commander
- GitHub Curator
- CI Doctor
- Runner Hardening Engineer
- Fleet Engineer
- Server Recovery Engineer
- Skill Librarian
- Security Reviewer
- Model Factory Engineer
- FormulaLM Researcher
- Frontend Engineer
- Backend/API Engineer
- Telegram Engineer
- Estimates QA
- Business Builder
- Finance Reporter
- Video Avatar Producer
- Documentation Curator
- Anti-Degradation Auditor

Communication channels:
- #command
- #github
- #ci
- #fleet
- #skills
- #models
- #business
- #finance
- #incidents
- #daily-summary

Every message must include:
- task_id;
- sender;
- role;
- target;
- status;
- summary;
- requested action;
- artifacts;
- blockers;
- next step.

Human language requirement:
Every agent must produce a human-readable summary, not just JSON.

Acceptance:
- team protocol exists;
- role files exist;
- handoff format exists;
- daily summary format exists;
- next task can spawn 5+ subagents with clear scopes.
```

---

# 16. P1 Anti-Degradation System

```text
TASK: P1_KOLIBRI_ANTI_DEGRADATION_SYSTEM

Goal:
Ensure Kolibri can self-develop without degrading architecture, tests, docs, GitHub state, server health, or model quality.

Create:
- docs/superfactory/19_OBSERVABILITY_AND_ANTI_DEGRADATION.md
- docs/superfactory/DEGRADATION_SIGNALS.md
- docs/superfactory/QUALITY_GATES.md
- docs/superfactory/SELF_REVIEW_LOOP.md
- docs/superfactory/WEEKLY_AUDIT.md
- docs/superfactory/DAILY_STATUS_TEMPLATE.md

Signals:
- tests missing;
- CI red;
- PR too large;
- docs stale;
- server disk low;
- node unreachable;
- runner false success;
- agent silent failure;
- required artifacts missing;
- dirty runtime repo drift;
- too many stale branches;
- secrets risk;
- cost spike;
- model quality regression.

Quality gates:
- no PR without scope;
- no PR without tests or documented test deferral;
- no task completed without required artifacts;
- no server cleanup without report;
- no model promotion without eval;
- no business/finance action without approval gate;
- no skill install without registry decision.

Required loop:
- daily status;
- weekly architecture review;
- PR size limit;
- dependency review;
- server health review;
- skill usefulness review;
- model eval review;
- revenue/cost review.

Acceptance:
- anti-degradation checklist exists;
- quality gates exist;
- weekly audit task exists;
- next exact audit command created.
```

---

# 17. P1 Rerun Integration Contract Audit

```text
TASK: P1_RERUN_P0_INTEGRATION_CONTRACT_AUDIT

Goal:
Rerun the P0 integration contract audit after unified Fabric API and runner hardening.

Read first:
- docs/superfactory/OPENAI_COMPATIBLE_FABRIC_API.md
- docs/superfactory/FABRIC_API_ENDPOINTS.md
- docs/agent/AGENT_RUNNER_CONTRACT.md
- docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/GLOBAL_DIGEST_FOR_CHATGPT.md
- previous failed audit artifacts if present

Create:
- docs/agent/integration/2026-06-30-p0-integration-contract-audit/EXECUTIVE_SUMMARY.md
- docs/agent/integration/2026-06-30-p0-integration-contract-audit/FRONTEND_BACKEND_CONTRACT.md
- docs/agent/integration/2026-06-30-p0-integration-contract-audit/ROUTE_DRIFT_REPORT.md
- docs/agent/integration/2026-06-30-p0-integration-contract-audit/CONTROL_PLANE_CONTRACT.md
- docs/agent/integration/2026-06-30-p0-integration-contract-audit/AGENT_HOST_TASK_CONTRACT.md
- docs/agent/integration/2026-06-30-p0-integration-contract-audit/DEPLOYED_UNITS_MAP.md
- docs/agent/integration/2026-06-30-p0-integration-contract-audit/MESH_CONTRACT.md
- docs/agent/integration/2026-06-30-p0-integration-contract-audit/TELEGRAM_GATEWAY_CONTRACT.md
- docs/agent/integration/2026-06-30-p0-integration-contract-audit/PROVIDER_ENV_REDACTED_INVENTORY.md
- docs/agent/integration/2026-06-30-p0-integration-contract-audit/DUPLICATION_REPORT.md
- docs/agent/integration/2026-06-30-p0-integration-contract-audit/RUNNER_SAFETY_REPORT.md
- docs/agent/integration/2026-06-30-p0-integration-contract-audit/P0_FIX_PLAN.md
- docs/agent/integration/2026-06-30-p0-integration-contract-audit/TEST_PLAN.md
- docs/agent/integration/2026-06-30-p0-integration-contract-audit/RISK_REGISTER.md
- docs/agent/integration/2026-06-30-p0-integration-contract-audit/PROJECT_DIGEST_PATCH_FOR_CHATGPT.md

Audit:
- frontend endpoints;
- backend routes;
- Control Plane routes;
- Agent Host task kinds;
- deployed systemd units;
- mesh hardcoded URLs;
- duplicated organism API;
- Telegram gateway responsibilities;
- provider/env names only, no values;
- Fabric API compatibility.

Do not fix code in this task.
Document exact mismatches and next patches.

Final response:
- status;
- files created;
- missing backend endpoints;
- unused backend routes;
- Agent Host supported task kinds;
- runner safety result;
- next implementation patch.
```

---

# 18. P1 Split PR #46

```text
TASK: P1_SPLIT_PR_46_FACTORY_AUTONOMY_PWA_BILLING

Goal:
Split giant PR #46 / `codex/factory-autonomy-pwa-billing` into reviewable, safe PRs.

Scope:
Analysis + branch split plan first.
Do not merge PR #46 as-is.

Read first:
- PR #46 body and diff
- docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/GLOBAL_DIGEST_FOR_CHATGPT.md
- integration audit results if available

Create:
- docs/superfactory/PR46_SPLIT_PLAN.md
- docs/superfactory/PR46_COMPONENT_MATRIX.md
- docs/superfactory/PR46_RISK_REGISTER.md
- docs/superfactory/PR46_TEST_PLAN.md

Split into candidate PRs:
1. PWA/frontend changes
2. billing scaffold
3. factory autonomy contracts
4. Agent Host runner/contracts, only if not already merged
5. deterministic estimates
6. FormulaLM remote-only harness
7. docs-only artifacts

For each component:
- files;
- purpose;
- dependencies;
- tests;
- risk;
- merge order;
- rollback;
- owner approval required yes/no.

Forbidden:
- do not mix billing with PWA;
- do not mix FormulaLM with runner hardening;
- do not mix server credential fixes with app code.

Acceptance:
- split plan created;
- safe extraction order defined;
- first extraction branch recommended.
```

---

# 19. P1 Server Skill Sync

```text
TASK: P1_SERVER_SKILL_SYNC_APPROVED_SKILLS_ONLY

Goal:
Sync approved Kolibri skills to all healthy server nodes.

Prerequisites:
- runner hardening complete;
- skill registry exists;
- skill security policy exists;
- fleet inventory exists;
- qjns/uiap disk blockers fixed or excluded.

Scope:
Sync approved skills only.
No unaudited internet code.
No root/global install unless documented.

Create:
- docs/superfactory/SERVER_SKILL_SYNC_REPORT.md
- docs/superfactory/SERVER_SKILL_STATUS.md
- docs/superfactory/SKILL_ROLLOUT_MATRIX.md

For each server:
- reachable method;
- repo path;
- skill version installed;
- sync status;
- skipped reason if any;
- test command;
- health result.

Rules:
- install only approve_server or approve_all_agents skills;
- do not run scripts unless approved;
- no secrets;
- no destructive actions;
- skip degraded nodes.

Acceptance:
- main and primary-candidate synced;
- all healthy reachable nodes synced or classified;
- qjns/uiap skipped if still degraded;
- skill usage docs updated.
```

---

# 20. P2 100K Logical Agent Scheduler

```text
TASK: P2_100K_LOGICAL_AGENT_SWARM_SCHEDULER_DESIGN

Goal:
Design how Kolibri can support up to 100000 logical agents across the fleet without crashing servers.

Important:
100000 logical agents are not 100000 physical processes.
They are lightweight state machines/tasks/roles scheduled over a limited worker pool.

Create:
- docs/superfactory/14_100K_LOGICAL_AGENTS.md
- docs/superfactory/AGENT_SWARM_SCHEDULER.md
- docs/superfactory/AGENT_RESOURCE_LIMITS.md
- docs/superfactory/AGENT_MEMORY_MODEL.md
- docs/superfactory/AGENT_QUEUE_POLICY.md

Design:
- logical_agent_id;
- role;
- memory pointer;
- skill set;
- task queue;
- priority;
- server affinity;
- budget;
- max runtime;
- retry policy;
- sleep/wake lifecycle;
- status;
- artifacts.

Physical limits:
- max concurrent workers per server;
- RAM limits;
- CPU limits;
- GPU limits;
- disk limits;
- network limits;
- queue backpressure.

Acceptance:
- architecture supports 100000 logical agents conceptually;
- physical worker limits are explicit;
- no server overload design;
- Control Plane/Fabric API extensions proposed.
```

---

# 21. P2 Local LLM Ring and Sovereign Model Factory

```text
TASK: P2_LOCAL_LLM_RING_AND_SOVEREIGN_MODEL_FACTORY_DESIGN

Goal:
Design Kolibri local LLM ring and sovereign model factory.

Owner intent:
No dependency on external inference providers.
Models should run in Kolibri-controlled infrastructure.
FormulaLM should improve, route, distill, evaluate, and specialize models.

Prerequisites:
- fleet hardware inventory;
- disk repaired on model candidates;
- runner hardened;
- Fabric API standard defined.

Create:
- docs/superfactory/12_LOCAL_LLM_RING.md
- docs/superfactory/13_MODEL_REGISTRY_AND_FORMULALM.md
- docs/superfactory/SOVEREIGN_MODEL_SUPERFACTORY.md
- docs/superfactory/SERVER_GPU_DISK_INVENTORY.md
- docs/superfactory/LOCAL_MODEL_REGISTRY_DESIGN.md
- docs/superfactory/MODEL_SELECTION_SHORTLIST.md
- docs/superfactory/MODEL_SERVING_STACK.md
- docs/superfactory/FORMULALM_INTEGRATION_PLAN.md
- docs/superfactory/IMAGE_GENERATION_STACK.md
- docs/superfactory/VISION_OCR_STACK.md
- docs/superfactory/EMBEDDINGS_RAG_STACK.md
- docs/superfactory/MODEL_LICENSE_REGISTER.md
- docs/superfactory/MODEL_EVAL_PLAN.md
- docs/superfactory/MODEL_GATEWAY_API_CONTRACT.md
- docs/superfactory/MODEL_ROLLOUT_PLAN.md

Design:
- local model registry;
- vLLM/SGLang text serving;
- llama.cpp/Ollama CPU/edge serving;
- ComfyUI/Diffusers image serving;
- TEI/embedding service;
- FormulaLM training/adapters/evals;
- model gateway;
- eval and promotion pipeline.

Do not:
- download huge models in this task;
- train models in this task;
- install GPU stacks blindly;
- ignore licenses.

Acceptance:
- no external inference provider required in target architecture;
- 5–10 initial model roles selected;
- FormulaLM integration plan documented;
- hardware prerequisites identified.
```

---

# 22. P2 Business Builder and Revenue Engine

```text
TASK: P2_KOLIBRI_BUSINESS_BUILDER_AND_REVENUE_ENGINE

Goal:
Enable Kolibri agents to create legal business opportunities to fund infrastructure.

Allowed:
- market research;
- product ideas;
- landing pages;
- proposals;
- outreach drafts;
- grant/free-credit discovery;
- invoices drafts;
- pricing pages;
- reports;
- lead lists from legal/public sources;
- CRM drafts;
- business plan drafts.

Forbidden:
- spam;
- fake accounts;
- scraping where prohibited;
- false identity;
- automatic financial transfers;
- bank account operations without owner approval;
- bypassing KYC/2FA/CAPTCHA;
- hidden subscriptions;
- violating platform terms.

Create:
- docs/superfactory/15_BUSINESS_ENGINE.md
- docs/superfactory/16_FINANCE_POLICY.md
- docs/superfactory/LEGAL_RESOURCE_SCOUT_POLICY.md
- docs/superfactory/REVENUE_TASKS.md
- .agents/roles/business-builder.md
- .agents/roles/finance-reporter.md

Money policy:
- agents may generate revenue opportunities;
- agents may prepare payment/invoice documents;
- agents may report expected revenue/costs;
- actual transfer/payment requires owner approval gate;
- all money movement must be logged.

Acceptance:
- business roles exist;
- finance policy exists;
- first 10 legal revenue experiments proposed;
- no automatic bank transfer implementation.
```

---

# 23. P2 Phone / Video Relay Observation Policy

```text
TASK: P2_PHONE_VIDEO_RELAY_OBSERVATION_POLICY

Goal:
Allow Kolibri agents to observe owner-approved phone/video relay safely.

Default mode:
Observation only.

Allowed:
- read screen state;
- summarize what is visible;
- detect notifications;
- assist owner during meetings;
- create reminders;
- prepare instructions.

Forbidden:
- entering bank credentials;
- approving payments;
- bypassing 2FA;
- sending messages without owner approval;
- registering accounts without approval;
- controlling apps that affect money/security without owner confirmation.

Create:
- docs/superfactory/17_PHONE_VIDEO_RELAY_POLICY.md
- docs/superfactory/PHONE_RELAY_APPROVAL_GATES.md

Acceptance:
- phone relay treated as observation by default;
- financial/security actions require explicit owner approval;
- forbidden cases documented.
```

---

# 24. P3 Video Avatar Meeting Layer

```text
TASK: P3_VIDEO_AVATAR_MEETING_LAYER

Goal:
Create a meeting layer where Kolibri agents can present status as video avatars.

Create:
- docs/superfactory/18_VIDEO_AVATAR_MEETINGS.md
- docs/superfactory/AVATAR_ROLES.md
- docs/superfactory/MEETING_FORMAT.md
- docs/superfactory/DAILY_STANDUP_AVATAR_SCRIPT.md
- docs/superfactory/WEEKLY_STRATEGY_AVATAR_SCRIPT.md

Avatar roles:
- Commander avatar;
- GitHub Curator avatar;
- Fleet Engineer avatar;
- Business Builder avatar;
- FormulaLM avatar;
- Finance Reporter avatar;
- Anti-Degradation Auditor avatar.

Meetings:
- daily standup;
- weekly strategy;
- incident review;
- PR review;
- business review;
- model factory review.

Acceptance:
- meeting scripts exist;
- first avatar prototype task created;
- no external paid provider required by default.
```

---

# 25. P3 Full Autopilot START Specification

```text
TASK: P3_FULL_AUTOPILOT_START_COMMAND_SPECIFICATION

Goal:
Define the future `START_KOLIBRI_SUPERFACTORY_AUTOPILOT` command.

Do not enable full autopilot yet.
This is specification only.

Prerequisites for future START:
- unified Fabric API active;
- command fabric HA active;
- runner hardening complete;
- GitHub always-current active;
- skill registry active;
- team mesh active;
- server inventory complete;
- degraded nodes classified;
- local LLM ring MVP ready;
- finance safety gates active;
- anti-degradation system active.

Create:
- docs/superfactory/FULL_AUTOPILOT_START_COMMAND.md
- docs/superfactory/AUTOPILOT_PRECHECKS.md
- docs/superfactory/AUTOPILOT_STOP_COMMAND.md
- docs/superfactory/AUTOPILOT_OBSERVABILITY.md
- docs/superfactory/AUTOPILOT_OWNER_DASHBOARD.md

On future START:
1. Commander reads current state.
2. GitHub Curator updates branch/PR/CI state.
3. Fleet Engineer updates server state.
4. Skill Librarian updates skill state.
5. CI Doctor reviews failures.
6. Business Builder proposes revenue tasks.
7. Model Factory Engineer checks local LLM ring.
8. Anti-Degradation Auditor checks drift.
9. Agents create daily plan.
10. Owner gets human-readable dashboard and video/avatar meeting summary.

Never:
- move money automatically;
- create accounts deceptively;
- bypass service rules;
- hide failures;
- overload servers;
- modify production without rollback.

Acceptance:
- START command spec exists;
- STOP command spec exists;
- prechecks are strict;
- owner dashboard fields defined.
```

---

# 26. Kwork Revenue Manager subagent

```text
ЗАДАЧА: СОЗДАТЬ СУБАГЕНТА KWORK REVENUE MANAGER И ОФОРМИТЬ ПРОФИЛЬ ПРОДАВЦА

Роль:
Ты — Codex-субагент с именем `Kwork Revenue Manager`.

Владелец:
Кочуров Владислав Евгеньевич.

Цель:
Помочь владельцу начать зарабатывать на Kwork: профессионально оформить профиль продавца, подготовить услуги/кворки, структуру портфолио, описания, цены, сроки, FAQ и ежедневный рабочий процесс.

Платформа:
https://kwork.ru/seller

Браузер:
Используй Яндекс Браузер через доступный инструмент управления компьютером/браузером.
Владелец уже авторизован.

Важно:
Не проси владельца снова входить в аккаунт, если сессия активна.
Не печатай пароли, cookies, токены, данные сессии, платёжные данные, коды из SMS/телефона или личные сообщения.
Не меняй банковские, платёжные и выводные реквизиты.
Не отправляй сообщения клиентам без подтверждения владельца.
Не создавай ложные обещания, фейковые отзывы, фейковое портфолио, фейковые регалии или вводящие в заблуждение гарантии.
Не занимайся спамом.
Не нарушай правила Kwork и пользовательское соглашение.
Не используй ботов для накрутки рейтинга, просмотров, отзывов или заказов.

Режим:
Помощник по оформлению профиля + создание бизнес-субагента.

Разрешённые действия:
- проверить текущий профиль продавца Kwork;
- определить, какие поля профиля не заполнены;
- подготовить профессиональный текст профиля;
- заполнить безопасные поля профиля, если это очевидно уместно;
- подготовить, но не публиковать чувствительные или необратимые изменения без подтверждения владельца;
- создать черновики кворков/услуг;
- подготовить описания портфолио;
- подготовить FAQ;
- подготовить ценовые пакеты;
- подготовить ежедневный план работы;
- создать локальную документацию для дальнейшей работы;
- создать переиспользуемый prompt/role-файл субагента.

Запрещённые действия:
- менять пароль, email, телефон или настройки безопасности;
- менять реквизиты выплат, банковские или платёжные данные;
- подключать платную рекламу/продвижение;
- принимать заказы клиентов без подтверждения владельца;
- отправлять исходящие предложения или сообщения без подтверждения владельца;
- давать невозможные гарантии;
- заявлять опыт, сертификаты или кейсы, которые владелец не предоставил;
- загружать чужие или защищённые авторским правом материалы как работы владельца;
- парсить или спамить покупателей;
- обходить лимиты платформы.

Создай локальные файлы:
- docs/business/kwork/KWORK_PROFILE_AUDIT.md
- docs/business/kwork/KWORK_PROFILE_COPY.md
- docs/business/kwork/KWORK_SERVICE_CATALOG.md
- docs/business/kwork/KWORK_PORTFOLIO_PLAN.md
- docs/business/kwork/KWORK_DAILY_OPERATING_SYSTEM.md
- docs/business/kwork/KWORK_RISK_AND_RULES.md
- docs/business/kwork/KWORK_NEXT_ACTIONS.md
- .agents/roles/kwork-revenue-manager.md

ШАГ 1 — Открыть профиль продавца:
Открой https://kwork.ru/seller.
Если аккаунт не авторизован, остановись и верни `blocked: login_required`.

Запиши только:
- какие разделы есть;
- какие поля профиля пустые;
- какие кворки уже есть;
- каких кворков не хватает;
- есть ли портфолио;
- есть ли аватар/обложка;
- есть ли описание профиля;
- выбраны ли категории;
- видны ли уровень продавца, рейтинг, заказы;
- что нужно улучшить.

ШАГ 2 — Позиционирование:
"AI-автоматизация, Telegram-боты, сайты, документы, сметы и агентские системы для бизнеса"

Сильные стороны:
- Kolibri AI Platform;
- AI-автоматизация;
- серверные агенты;
- Telegram-боты;
- backend/frontend;
- документы и сметы;
- бизнес-процессы;
- AI-продукты;
- GitHub/DevOps/agent workflows.

Не пиши “гарантирую доход” или “100% результат”.

ШАГ 3 — Текст профиля:
Создай KWORK_PROFILE_COPY.md:
- 4 варианта заголовка;
- 3 коротких описания;
- полное описание;
- теги/ключевые слова.

ШАГ 4 — Каталог услуг:
Создай 10 кворков:
1. Создам Telegram-бота с AI-ассистентом для вашего бизнеса
2. Настрою AI-автоматизацию рутинной задачи
3. Сделаю простой сайт/лендинг для услуги или продукта
4. Проведу аудит сайта и дам план улучшений
5. Создам AI-ассистента для документов и текстов
6. Автоматизирую обработку заявок, таблиц или документов
7. Сделаю интеграцию с API или вебхуком
8. Проверю и улучшу код Python/JavaScript-проекта
9. Подготовлю MVP AI-сервиса или бота
10. Сделаю структуру промптов и сценариев для AI-агента

Для каждого:
- название;
- категория;
- короткое описание;
- что входит;
- что не входит;
- срок;
- базовый/стандартный/премиум пакет;
- add-ons;
- требования к покупателю;
- FAQ;
- идея портфолио;
- риски;
- правила правок.

ШАГ 5 — Безопасно заполнить профиль:
Заполни безопасные поля.
Перед нажатием `Сохранить`, `Опубликовать`, `Отправить` покажи владельцу резюме и запроси подтверждение.

Не менять:
- выплаты;
- email;
- телефон;
- пароль;
- безопасность;
- юридические/налоговые настройки;
- платное продвижение.

ШАГ 6 — Первый кворк:
Черновик:
“Создам Telegram-бота с AI-ассистентом для вашего бизнеса”

Не публикуй без подтверждения владельца.

ШАГ 7 — Портфолио:
Создай KWORK_PORTFOLIO_PLAN.md:
- Kolibri AI Platform;
- Telegram bot examples;
- AI document assistant demo;
- website audit example;
- automation workflow;
- GitHub/DevOps/agent workflow.

ШАГ 8 — Ежедневная система:
Создай KWORK_DAILY_OPERATING_SYSTEM.md:
- проверить сообщения;
- проверить заказы;
- улучшить кворк;
- добавить пример в портфолио;
- этично проанализировать конкурентов;
- отвечать на лиды только вручную или owner-approved;
- отслеживать просмотры/заказы/конверсию;
- ежедневный отчёт.

ШАГ 9 — Риски:
Создай KWORK_RISK_AND_RULES.md:
- без спама;
- без фейковых отзывов;
- без фейкового портфолио;
- без манипуляций рейтингом;
- без обхода внешней оплаты;
- без нереалистичных обещаний;
- без скрытых подписок;
- без утечки данных клиентов;
- без финансовых действий без подтверждения.

Финальный ответ:
- статус;
- какие разделы проверены;
- какие изменения подготовлены;
- применены ли изменения профиля;
- создан ли первый черновик;
- опубликован ли первый кворк;
- что требует подтверждения;
- следующие 5 действий;
- созданные файлы;
- блокеры.

Не заявляй, что доход уже получен.
```

---

# 27. Short emergency snippets

## 27.1. Агент не должен делать локально

```text
Ты не локальный разработчик. Ты Mac thin-client dispatcher.

Не реализуй product code на Mac.
Думай, планируй, создавай envelopes, отправляй задачи в удалённую Kolibri Factory, используй primary-candidate/main/Home/Primorye/MIMO/API agents, следи за статусами, собирай artifacts.

Любая разработка должна иметь remote task_id, target node/agent pool, status, result artifact и PR/branch.

Сейчас отправь P0_AGENT_HOST_GENERIC_RUNNER_CONTRACT_HARDENING_2026_06_30 в удалённую фабрику. Mac не реализует, Mac только командует и наблюдает.
```

## 27.2. Агент не должен отвечать “сервер недоступен”

```text
Никогда не отвечай “сервер недоступен” как тупик.

Если прямой путь недоступен:
1. определи причину;
2. найди fallback route;
3. отправь задачу через API relay / Control Plane / Primorye / Home / main / primary-candidate;
4. создай repair task для проблемного узла;
5. верни structured status.

Ответ должен содержать:
- node;
- status;
- reason;
- fallback_nodes;
- route_used;
- task_id;
- repair_task;
- next_action.
```

## 27.3. GitHub должен быть всегда актуален

```text
GitHub is source of truth.

Каждая задача должна иметь:
- branch;
- PR or issue;
- task_id;
- CI/status;
- artifacts;
- current description;
- scope and explicitly not included;
- tests run or test deferral reason;
- next action.

Не делай просто PR. Веди GitHub как операционную систему проекта.
```

## 27.4. Фабрика работает как команда

```text
Agents must communicate like a human team.

Every handoff must include:
- task_id;
- sender role;
- receiver role;
- context;
- scope;
- artifacts;
- blockers;
- requested action;
- next step;
- owner-readable summary.
```

## 27.5. Безопасность полной автономии

```text
Full authority does not mean destructive chaos.

Never:
- print secrets;
- push to main;
- force push;
- bypass CI;
- delete dirty work;
- install unaudited internet code on servers;
- abuse free resources;
- move money automatically;
- use phone relay for bank/security approvals;
- mark completed with missing artifacts.
```

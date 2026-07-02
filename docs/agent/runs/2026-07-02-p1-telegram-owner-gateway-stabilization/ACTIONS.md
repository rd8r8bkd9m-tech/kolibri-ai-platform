# Actions

Implemented:
- Added redacted Russian summary formatters for `/nodes`, `/agents`, and `/queue`.
- Replaced raw node/agent/queue command output with owner-safe summaries.
- Added a guarded `submit_chat_task` Control Plane failure path that sends a human Russian fallback instead of leaking technical exception text through the polling loop.
- Added fake Telegram/fake Control Plane regression tests for command summary redaction and chat queue failure redaction.

Guardrails observed:
- No live Telegram Bot API calls.
- No webhook, polling receiver, service, deploy, credential, or destructive git operation changes.
- No frontend/web portal/Mini App/backend billing/model-gateway/Control Plane runtime repair files touched.
- No push to main or force push.

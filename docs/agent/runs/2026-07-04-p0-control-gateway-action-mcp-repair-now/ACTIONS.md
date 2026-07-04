# ACTIONS

- Continued branch `p0/governing-chat-mcp-action-start-factory-20260704`.
- Merged remote PR #166 branch into the local branch and resolved add/add conflicts using the current remote PR files as baseline.
- Repaired `ops/chatgpt_action_gateway.py`.
- Added `KOLIBRI_FACTORY_CONTROL_URLS` fallback support.
- Added `/v1/github/prs` action route with a safe partial response instead of shelling out or reading GitHub secrets.
- Added safe Start Factory canary submission through `/v1/agents/tasks`.
- Added `ops/systemd/kolibri-chatgpt-action-gateway.service` as a deploy draft.
- Added/updated gateway tests.
- Ran live Control Plane probes and two safe canary attempts.

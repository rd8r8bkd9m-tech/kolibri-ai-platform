# Owner Setup Guide

1. Deploy `ops/chatgpt_action_gateway.py` near the Control Plane.
2. Set `KOLIBRI_FACTORY_CONTROL_URL` to the authoritative Control Plane URL.
3. Set `KOLIBRI_CHATGPT_ACTION_TOKEN` in the runtime environment.
4. Expose the gateway behind HTTPS.
5. Import `CHATGPT_ACTION_OPENAPI.yaml` into the owner Action/MCP client.
6. Test `GET /v1/action/health`.
7. Run `POST /v1/factory/start` in dry-run mode before allowing task submission.

Do not put the token into repo files or chat transcripts.

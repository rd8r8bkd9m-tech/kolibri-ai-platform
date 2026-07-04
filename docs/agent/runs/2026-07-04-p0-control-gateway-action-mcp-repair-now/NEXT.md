# NEXT

1. Owner approves production canary deploy of `kolibri-chatgpt-action-gateway.service`.
2. Repair active Agent Host lease path so `owner_remote_task` canary is leased promptly.
3. Re-run `POST /v1/factory/start` until a collectable content-bearing artifact exists.
4. Bind `https://action.kolibriai.ru` to the gateway through nginx or Cloudflare Tunnel.
5. Paste `CHATGPT_ACTION_OPENAPI.yaml` into GPT Builder Actions and test `/v1/action/health`.

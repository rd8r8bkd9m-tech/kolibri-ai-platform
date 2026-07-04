# OWNER_SETUP_GUIDE

## OpenAPI file

```text
docs/agent/runs/2026-07-04-p0-control-gateway-action-mcp-repair-now/CHATGPT_ACTION_OPENAPI.yaml
```

## Action URL

Production URL to use after deploy:

```text
https://action.kolibriai.ru
```

Current local runtime draft binds to:

```text
http://127.0.0.1:9197
```

## Env

```text
KOLIBRI_CHATGPT_ACTION_TOKEN
KOLIBRI_FACTORY_CONTROL_URLS=http://10.99.0.10:9101,http://10.99.0.2:9101,http://10.99.0.1:9101
```

Never paste the token into logs or chat. The gateway reports only `token_present=true/false`.

## GPT Builder setup

1. Open GPT Builder.
2. Open Actions.
3. Add Action.
4. Paste `CHATGPT_ACTION_OPENAPI.yaml`.
5. Auth: API Key / Bearer.
6. Header: `Authorization`.
7. Value: `Bearer <token>`.
8. Test `GET /v1/action/health`.

## First owner commands after connection

```text
Проверь здоровье фабрики
Старт фабрики
Покажи очередь
Запусти safe task
```

## Expected health result

The response must include:

- `status`
- `control_plane_used`
- `fallback_nodes`
- `token_present`
- no secrets

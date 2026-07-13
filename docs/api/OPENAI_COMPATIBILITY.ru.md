# OpenAI-compatible API Kolibri V2.1

Kolibri предоставляет публичную поверхность `/v1` с единственной публичной моделью `kolibri`.

## Аутентификация

Для SDK и серверных интеграций используется стандартный Bearer-заголовок:

```http
Authorization: Bearer sk-kolibri-...
```

Ключ создаётся один раз через `POST /v1/api-keys`, в ответе показывается один раз, а в SQLite/PostgreSQL хранится только SHA-256. Для browser Shell используется подписанная Secure HttpOnly cookie; upstream provider key клиенту никогда не передаётся.

Пример создания developer key из owner-сессии:

```bash
curl -X POST http://127.0.0.1:8191/v1/api-keys \
  -H "Authorization: Bearer $KOLIBRI_OWNER_SESSION" \
  -H "Content-Type: application/json" \
  -d '{"name":"local-sdk","role":"developer"}'
```

Ключи можно перечислить без raw secret и отозвать:

```text
GET    /v1/api-keys
DELETE /v1/api-keys/{key_id}
```

Production bootstrap keys допускаются через root-readable `KOLIBRI_API_KEYS_FILE`; raw значения используются только при старте, а в базе сохраняются hashes.

## Нативные ресурсы

- Responses: create, retrieve, streaming/resume, events, cancel, delete, input items, token count и compaction;
- Conversations/Projects и messages;
- Chat Completions;
- Models;
- Realtime WebSocket;
- Estimates, revisions, exports и artifacts;
- Runtime, tasks, nodes, leases, fencing и evidence.

Пример с OpenAI SDK-совместимой конфигурацией:

```python
from openai import OpenAI

client = OpenAI(
    api_key="<KOLIBRI_API_KEY>",
    base_url="https://kolibriai.ru/v1",
)
response = client.responses.create(
    model="kolibri",
    input="Сделай предварительную смету дома 100 м² в Лениногорске",
)
print(response.output_text)
```

## Provider-owned семейства

Media/admin/tool resources проксируются server-side только при наличии entitlement и scoped credential. Gateway поддерживает method/query/body, multipart/binary и SSE. Публичные `OpenAI-Project` и `OpenAI-Organization` не определяют upstream scope: используются только server-side значения.

Без provider-конфигурации gateway fail-closed:

```json
{
  "error": {
    "message": "The OpenAI-compatible resource '/v1/images/generations' is not configured on this deployment.",
    "type": "server_error",
    "param": null,
    "code": "upstream_not_configured"
  }
}
```

Обычный клиент Shell не может вызывать generic provider gateway. Он доступен developer/owner key; `organization/*` — только owner.

## Realtime

`/v1/realtime` требует Bearer key или signed session. Неавторизованное соединение получает OpenAI-shaped error и закрывается с кодом `4401`.

## Источник правды

Машинная матрица: `packages/contracts/openai-compatibility.json`.
OpenAPI: `packages/contracts/openapi.json`.

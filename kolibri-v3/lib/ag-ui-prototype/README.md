# AG-UI prototype transport

Слой транспорта для прототипа AI-чата: AG-UI события через SSE поверх `fetch`.

## Состав

- `types.ts` — типы событий AG-UI, `AgentTransport`, `A2AClient`;
- `transport.ts` — production-ready `FetchAGUITransport` (SSE-парсер, `AbortController`);
- `mock-transport.ts` — `MockAGUITransport` для локального прототипа;
- `reducer.ts` — `chatReducer` и `initialChatState`;
- `use-agui-chat.ts` — React-хук, подключающий транспорт к состоянию.

## Контракт backend

```http
POST /api/agent/run
Accept: text/event-stream
Content-Type: application/json
```

Тело запроса:

```json
{
  "threadId": "thread-123",
  "runId": "run-456",
  "input": "Собери сводку продаж за неделю",
  "messages": [
    { "id": "message-1", "role": "user", "content": "Собери сводку продаж за неделю" }
  ],
  "agentId": "analytics-agent",
  "model": "light"
}
```

Ответ — SSE, каждый блок завершается пустой строкой:

```text
data: {"type":"RUN_STARTED","threadId":"thread-123","runId":"run-456"}

data: {"type":"TEXT_MESSAGE_START","messageId":"message-789","role":"assistant"}

data: {"type":"TEXT_MESSAGE_CONTENT","messageId":"message-789","delta":"Собираю "}

data: {"type":"TEXT_MESSAGE_END","messageId":"message-789"}

data: {"type":"RUN_FINISHED","threadId":"thread-123","runId":"run-456"}

data: [DONE]
```

## Подключение

Endpoint задаётся конфигурацией:

```env
NEXT_PUBLIC_AG_UI_ENDPOINT=/api/agent/run
```

Авторизация передаётся через `getHeaders`:

```ts
new FetchAGUITransport(endpoint, () => ({
  Authorization: `Bearer ${token}`,
}));
```

Отмена запроса — `transport.cancel()` (abort fetch). При `RUN_ERROR` reducer
переводит состояние в `error` и завершает стрим. Неизвестные типы событий
логируются и пропускаются.

## Замена mock на реальный транспорт

Интерфейс `AgentTransport` один для mock и реального транспорта. Для
подключения реального AG-UI backend достаточно заменить фабрику в
`useAGUIChat` и указать endpoint через конфигурацию.

> Токены, URL и секреты не зашиты в код — они приходят только через
> конфигурацию или `getHeaders`.

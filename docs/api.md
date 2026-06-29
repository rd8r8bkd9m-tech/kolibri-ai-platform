# API Kolibri

Документ фиксирует публичные и внутренние API-контракты проекта. Он должен
обновляться при каждом изменении backend, Control Plane, agent host, платежей
или сметчика.

## Базовые адреса

| Контур | Адрес |
| --- | --- |
| Публичное приложение | `http://104.253.43.117` |
| Backend API | `/api/*` |
| WebSocket chat | `/ws/chat` |
| Control Plane mesh | `http://10.99.0.2:9101` |

## Пользовательский backend

| Метод | Endpoint | Назначение |
| --- | --- | --- |
| `POST` | `/api/chat` | Чат с выбранным AI-провайдером |
| `GET` | `/api/providers` | Доступные провайдеры моделей |
| `GET` | `/api/knowledge` | Список документов базы знаний |
| `POST` | `/api/knowledge/upload` | Загрузка документа |
| `POST` | `/api/knowledge/search` | Поиск по базе знаний |
| `GET` | `/api/factory/status` | Сводка фабрики для интерфейса |
| `GET` | `/api/billing/plans` | Тарифы подписок |
| `POST` | `/api/billing/checkout` | Создание платежа или fallback-заявки |
| `POST` | `/api/billing/tbank/notification` | Callback T-Банк |
| `POST` | `/api/billing/tbank/charge-due` | Админский запуск списаний |

## Control Plane

| Метод | Endpoint | Назначение |
| --- | --- | --- |
| `GET` | `/health` | Health check Control Plane и Redis |
| `GET` | `/v1/nodes` | Зарегистрированные узлы фабрики |
| `POST` | `/v1/nodes/register` | Регистрация Agent Host |
| `POST` | `/v1/nodes/<node_id>/heartbeat` | Heartbeat узла |
| `POST` | `/v1/nodes/<node_id>/drain` | Включить или снять drain |
| `POST` | `/v1/tasks` | Создать задачу |
| `GET` | `/v1/tasks?summary=1&compact=1` | Компактный список задач |
| `GET` | `/v1/tasks/<task_id>` | Детали задачи |
| `POST` | `/v1/tasks/lease` | Выдать lease агенту |
| `POST` | `/v1/tasks/<task_id>/heartbeat` | Heartbeat задачи |
| `POST` | `/v1/tasks/<task_id>/complete` | Завершить задачу |
| `POST` | `/v1/tasks/<task_id>/fail` | Зафиксировать ошибку |
| `POST` | `/v1/tasks/<task_id>/cancel` | Отменить задачу |
| `POST` | `/v1/agent-messages` | Опубликовать сообщение агента |
| `GET` | `/v1/agent-messages?target=all` | Общая лента агентов |

## Формат agent message

```json
{
  "sender": "node-id",
  "recipients": ["all"],
  "kind": "task_completed",
  "topic": "generic_implementation",
  "task_id": "KOL-DOCS-STEWARD-20260629",
  "body": "Документация обновлена",
  "artifacts": [
    {"result_path": "/var/lib/kolibri-agent/artifacts/.../result.json"}
  ]
}
```

## Сметы

Детерминированные сметы должны сохранять одинаковый результат для одинаковых
вводных, версии прайсбука и региона. Для проверки используется canonical input
hash, deterministic estimate id и фиксированный pricebook version.

## Платежи

T-Банк подключается через переменные окружения:

- `TBANK_TERMINAL_KEY`
- `TBANK_PASSWORD`
- `TBANK_API_URL`
- `KOLIBRI_PUBLIC_URL`

Если T-Банк не настроен, checkout сохраняет fallback-заявку и не создаёт
активную подписку.

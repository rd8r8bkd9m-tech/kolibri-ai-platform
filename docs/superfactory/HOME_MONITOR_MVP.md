# Home Control Center Monitor — MVP Plan

## Назначение

Home Monitor (Диспетчер) — локальная панель мониторинга для владельца Kolibri AI
Control Center. Отображает состояние фабрики, очередь задач, здоровье узлов и
.wallboard в едином интерфейсе на русском языке.

## Архитектура

```
Owner Browser
  → Frontend (React 19 + Vite)
    → GET /api/home/monitor     → home_monitor.py → factory_status.py → Control Plane API
    → GET /api/home/wallboard   → home_monitor.py → factory_status.py → Control Plane API
    → GET /api/factory/status   → factory_status.py → Control Plane API (wallboard legacy)
```

## Текущие компоненты

| Компонент | Путь | Описание |
| --- | --- | --- |
| Backend модуль | `backend/home_monitor.py` | Агрегация статуса фабрики, задач, узлов для мониторинга |
| Backend endpoints | `backend/main.py` | `/api/home/monitor`, `/api/home/wallboard` |
| Frontend компонент | `frontend/src/App.jsx` | `MonitorView` — вкладка "Диспетчер" |
| Тесты | `tests/test_home_monitor.py` | Контрактные тесты для бэкенда и проверка фронта |
| Навигация | `frontend/src/App.jsx` | Вкладка "Диспетчер" в сайдбаре |

## Существующие сервисы

### Factory Control (`ops/factory_control.py`)

Redis-backed control plane sidecar. Основные контракты:

- `GET /v1/health` — здоровье control plane
- `GET /v1/nodes` — список узлов с heartbeat
- `POST /v1/nodes/register` — регистрация узла
- `POST /v1/nodes/{id}/heartbeat` — heartbeat узла
- `POST /v1/tasks/lease` — аренда задачи узлом
- `GET /v1/tasks` — список задач
- `POST /v1/tasks` — создание задачи
- `POST /v1/tasks/{id}/complete` — завершение задачи
- `POST /v1/tasks/{id}/fail` — пометка задачи как ошибочной

### Factory Status (`backend/factory_status.py`)

Нормализует данные control plane для фронтенда:

- `build_factory_status()` — построение агрегированного статуса
- `fetch_factory_status()` — запрос к control plane API
- Узлы: heartbeat freshness (fresh/degraded/stale), RAM, CPU, disk
- Задачи: queue size, task states breakdown
- Роли: на русском (Директор, Инженер, Ревьюер, etc.)

### Frontend Cluster View (wallboard)

Вкладка "Сеть" в сайдбаре:

- Статистика: Свежие, Деградируют, Устарели, Задач в очереди
- Карточки узлов: имя, роль, heartbeat, RAM, CPU
- Автообновление каждые 15 секунд

### Agent Host (`ops/agent_host.py`)

Удалённый хост агента. Поддерживает:

- Регистрацию и heartbeat
- Аренду задач
- Выполнение через MIMO Auto / Codex / API / Local LLM
- Permission packs и push-контракты
- Canonical run artifacts (PLAN.md, ACTIONS.md, TESTS.md, RESULT.md, NEXT.md)

## Home Monitor (Диспетчер) — MVP

### API Endpoints

| Endpoint | Описание |
| --- | --- |
| `GET /api/home/monitor` | Полный статус мониторинга: флот, задачи, узлы, preferences |
| `GET /api/home/wallboard` | Wallboard с отсортированным списком задач |

### Monitor Response Structure

```json
{
  "status": "online",
  "generated_at": "2026-07-02T10:00:00Z",
  "preferences": {
    "ai_runner": "mimo-auto",
    "owner_language": "ru",
    "display_format": "wallboard",
    "auto_refresh_seconds": 15,
    "default_task_runner": "mimo"
  },
  "fleet": {
    "total_nodes": 6,
    "fresh_nodes": 4,
    "degraded_nodes": 1,
    "stale_nodes": 1,
    "free_ram_gb": 24.5,
    "total_ram_gb": 48.0,
    "avg_cpu_percent": 35.2
  },
  "tasks": {
    "total": 12,
    "active": 3,
    "completed": 8,
    "failed": 1,
    "queue_size": 2,
    "states": { "queued": 2, "running": 1, "completed": 8, "failed": 1 }
  },
  "nodes": [
    {
      "node_id": "home",
      "name": "Связной",
      "role": "command_node_gateway",
      "status": "online",
      "freshness": "fresh",
      "status_label": "Онлайн",
      "active_task": null,
      "ram": "6.0/7.8 GB",
      "cpu": 4
    }
  ]
}
```

### Frontend UI

Вкладка "Диспетчер" в сайдбаре:

1. **Шапка**: название,.runner (mimo-auto), интервал обновления
2. **Статистика**: узлов онлайн, очередь, активные, завершено, RAM
3. **Узлы фабрики**: карточки с именем, ролью, статусом, активной задачей
4. **Задачи**: список до 20 задач с task_id, kind, state, objective, node

### Предпочтения Home-side

| Параметр | Значение | Описание |
| --- | --- | --- |
| ai_runner | `mimo-auto` | AI runner по умолчанию для Home |
| owner_language | `ru` | Русский язык для UI и сообщений |
| display_format | `wallboard` | Формат отображения |
| auto_refresh_seconds | `15` | Интервал автообновления |
| default_task_runner | `mimo` | Runner для задач Home |

## Домены узлов

| Node ID | Роль | Display Name | API Paths |
| --- | --- | --- | --- |
| home | command_node_gateway | Связной | fabric_api, fallback_relay |
| main | control_plane | Директор | fabric_api, control_plane_api, artifact_api |
| 9fts | implementation_model_node | Инженер | fabric_api, agent_host_api, model_node_api, fallback_relay |
| new | review_agent | Ревьюер | fabric_api, agent_host_api, fallback_relay |
| uiap | knowledge_model_node | Знания | fabric_api, fallback_relay |
| qjns | remote_agent | Тестировщик | fabric_api, agent_host_api, fallback_relay |

## Команды запуска

### Локальная разработка

```bash
# Backend
cd backend && python -m uvicorn main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend && npm run dev

# Factory control sidecar
python3 ops/factory_control.py --host 127.0.0.1 --port 9101
```

### Просмотр

```bash
# Открыть в браузере
open http://localhost:5173

# Или через backend
open http://localhost:8000

# API мониторинга
curl http://localhost:8000/api/home/monitor
curl http://localhost:8000/api/home/wallboard
```

### Тесты

```bash
python3 -m pytest tests/test_home_monitor.py -v
python3 -m pytest tests/test_factory_status.py -v
```

## Приёмочные критерии

- [x] Home local task принимается и может быть арендован Home/home-live
- [x] Task использует MIMO Auto preference для Home-side разработки
- [x] Owner-facing имена, роли и инструкции на русском и human-readable
- [x] Существующий wallboard/session status задокументирован
- [x] Первый MVP план Home monitor создан
- [x] Владелец получает точную команду view/attach или точный блокер
- [x] Нет секретов и деструктивных изменений

## Follow-up tasks

1. Добавить WebSocket для real-time обновлений wallboard
2. Добавить фильтрацию задач по state, node, kind
3. Добавить action-кнопки: cancel task, drain node
4. Добавить歷史任务历史 (task history) с пагинацией
5. Добавить алерты при degraded/stale узлах
6. Интеграция с Telegram для уведомлений о статусе

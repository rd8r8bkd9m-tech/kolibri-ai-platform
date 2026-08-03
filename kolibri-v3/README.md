# Колибри V3

Новый chat-first продукт Kolibri. Web-интерфейс создан на официальных
примитивах `assistant-ui`, использует AG-UI как потоковый runtime и работает с
новым изолированным V3 backend. Старый `kolibri-backend` не является upstream
или fallback для этого приложения.

## Каноническая структура

Весь активный продукт расположен внутри этой папки:

- browser desktop/PWA: `app/`, `components/`, `lib/`;
- React Native / Expo: `apps/kolibri-mobile/`;
- backend и миграции: `backend/`;
- Rust-ядра: `packages/`;
- deploy: `deploy/`;
- документация и release evidence: `docs/`, `release/`.

См. [`docs/SOURCE_OF_TRUTH.md`](docs/SOURCE_OF_TRUTH.md) и
[`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md). Родительские приложения не
являются частью V3.

Основная рабочая поверхность:

- слева — проекты, задачи и история диалогов;
- в центре — один assistant-ui Thread и контекстный Canvas;
- справа — проверка, файлы и безопасные представления рабочих инструментов;
- на узком экране — один чат и модальные панели навигации/контекста.

Дизайн намеренно использует спокойную нейтральную геометрию Codex-подобного
desktop-приложения, но остаётся самостоятельным продуктом с брендом «Колибри».
Первый продуктовый вертикальный срез: реальный пользовательский аккаунт,
персональные настройки, MiMo Code / Codex CLI, долговечные диалоги и
автоматическое создание проектного контекста из первого сообщения.

## Запуск

Backend:

```bash
python -m venv backend/venv
backend/venv/bin/python -m pip install -r backend/requirements-dev.txt
npm run dev:backend
```

`dev:backend` всегда запускается из корня V3, использует рабочую базу
`var/kolibri-v3.db` и явно включает единый direct/dev runtime. Для временных
QA-баз и отключённых runtime используются отдельные порты, а не `8002/3103`.

Для обычной разработки запускайте единый supervisor:

```bash
npm run dev
```

Он поднимает web и канонический V3 backend вместе и автоматически
перезапускает любой из процессов после неожиданной остановки. Фоновый
`launchd` здесь не используется: macOS не разрешает LaunchAgent читать
исходники из защищённой папки `Documents`, а dev‑режим должен сохранить
полный доступ к рабочей области агентов.

Чтобы supervisor не зависел от текущего терминала или сессии Codex, используйте
фоновую пользовательскую `screen`‑сессию:

```bash
npm run dev:persistent
npm run dev:persistent:status
```

Она всё равно делегирует запуск только каноническому `npm run dev`; миграция
рабочей БД и проверка единственного platform owner выполняются до открытия
портов. Для просмотра живого вывода: `screen -r kolibri-v3-dev`, для
контролируемого перезапуска: `npm run dev:persistent:restart`. Вывод
preflight и процессов также сохраняется в `var/dev-runtime/screen.log`.
Остановка считается завершённой только после освобождения обоих портов
`8002/3103`; это не позволяет следующему запуску подключить frontend к
осиротевшему или постороннему backend.

`npm run dev:stack` оставлен как явный алиас той же команды.
`npm run dev:web` намеренно заблокирован: frontend-only запуск мог подключиться
к устаревшему или чужому процессу на порту `8002` и обойти миграции и проверку
суперадмина.

В локальной development-среде backend поднимает один постоянный
`codex app-server` при старте и завершает его при остановке. Все чаты работают
через этот процесс; для каждого сообщения новый `codex exec` не запускается.
Codex-thread изолирован по tenant/chat и остаётся ephemeral, а каноническая
история по-прежнему хранится только в V3 Product/Data backend. Совместимый
локальный профиль по умолчанию — `gpt-5.5` с `low` effort; значения доступны
через `KOLIBRI_V3_CODEX_MODEL` и `KOLIBRI_V3_CODEX_EFFORT`.

Durable worker MiMo Code / Codex CLI запускается отдельным процессом и
обращается только к Logical Home:

```bash
PYTHONPATH=backend backend/venv/bin/python -m app.product_run_worker
```

Для worker задаются `KOLIBRI_V3_HOME_PRODUCT_COMMAND_URL`, Product authority
grant и закрытые service credentials через `*_FILE`; сами MiMo/Codex
credentials остаются на Primary.
Если контур Home не настроен, chat fail-closed и не подменяет ответ демо-текстом.

Secretless-запросы на подключение провайдеров обрабатывает отдельный worker:

```bash
PYTHONPATH=backend backend/venv/bin/python -m app.provider_enrollment_worker
```

Next/BFF не содержит provider-authority token и не обращается к Primary.
Product/Data хранит только tenant-scoped статус, точный enrollment intent и
hash подтверждения. При отсутствии Primary responder intent фиксируется
fail-closed; `connected` появляется только после валидированного authority
status либо успешного terminal run через Logical Home → A2A → Primary.

Web:

```bash
npm run dev
```

Интерфейс: <http://127.0.0.1:3103/app>

Публичная регистрация всегда создаёт обычного пользователя. Чтобы назначить
первого владельца в локальной среде, сначала зарегистрируйте аккаунт, затем
выполните доверенную серверную команду:

```bash
PYTHONPATH=backend backend/venv/bin/python -m app.owner_bootstrap \
  --email owner@example.com
```

В production email дополнительно фиксируется через
`KOLIBRI_V3_BOOTSTRAP_OWNER_EMAIL`. HTTP endpoint для повышения роли
намеренно отсутствует.

Настройки окружения перечислены в `.env.example`. Секрет MiMo и состояние
официального `codex login` остаются только на изолированном Provider Execution
Authority. V3 backend и браузер получают только безопасный статус.

## MCP серверы и агентные инструменты

V3 использует MCP (Model Context Protocol) серверы для подключения инструментов
к Codex CLI и MiMo Code. Это позволяет агентам использовать реальные данные
(погода, расценки, нормативные документы) вместо хардкода.

### Архитектура

```
Codex CLI (app-server --stdio)
  ├── web_search="live" (встроенный поиск)
  ├── kolibri-weather MCP → get_weather()
  ├── kolibri-pricing MCP → search_prices(), get_reference_prices()
  └── kolibri-normative MCP → search_normative(), get_normative_document()

MiMo API (function calling)
  ├── web_search (нативный)
  ├── get_weather (function calling)
  ├── search_prices (function calling)
  └── search_normative (function calling)
```

### MCP серверы

| Сервер | Файл | Инструменты | Источник данных |
|--------|------|-------------|-----------------|
| `kolibri-weather` | `backend/mcp/weather_server.py` | `get_weather` | Open-Meteo API |
| `kolibri-pricing` | `backend/mcp/pricing_server.py` | `search_prices`, `get_reference_prices` | ФГИС ЦС + справочные расценки |
| `kolibri-normative` | `backend/mcp/normative_server.py` | `search_normative`, `get_normative_document` | CNTD (ГЭСН/ТЕР/СП) |

### Запуск end-to-end пайплайна

1. **Установите MCP серверы в Codex CLI:**

```bash
codex mcp add kolibri-weather -- python3 backend/mcp/weather_server.py
codex mcp add kolibri-pricing -- python3 backend/mcp/pricing_server.py
codex mcp add kolibri-normative -- python3 backend/mcp/normative_server.py
```

2. **Проверьте подключение:**

```bash
codex mcp list
```

3. **Отправьте тестовый запрос:**

```bash
# Погода
codex exec "Какая погода в Москве? Используй kolibri-weather/get_weather."

# Расценки
codex exec "Найди расценки на штукатурку стен. Используй kolibri-pricing/search_prices."

# Нормативка
codex exec "Найди ГЭСН на бетонные работы. Используй kolibri-normative/search_normative."

# Смета (полный пайплайн)
codex exec "Составь смету на штукатурку 20 м². Сначала найди расценки через kolibri-pricing/search_prices."
```

4. **Через Python (для интеграции в backend):**

```python
import json
from backend.mcp.weather_server import server as weather
from backend.mcp.pricing_server import server as pricing

# Call tool directly
handler = weather._handlers["get_weather"]
result = handler(location="Moscow", forecast_days=3)
print(json.dumps(result, ensure_ascii=False, indent=2))
```

### Константы (единый источник правды)

Все URL, модели, таймауты, цвета и строительные defaults вынесены в
`backend/app/constants.py`. Модули импортируют константы вместо хардкода:

```python
from .constants import MIMO_BASE_URL_DEFAULT, TIMEOUT_FGIS, PDF_COLOR_TEAL
```

### AGENTS.md и Skills

Агентное поведение определяется в `.agents/AGENTS.md` и скиллах в
`.agents/skills/`. Codex CLI и MiMo Code читают эти файлы автоматически.

### Переменные окружения

| Переменная | Описание | По умолчанию |
|-----------|----------|--------------|
| `KOLIBRI_V3_MIMO_BASE_URL` | URL MiMo API | `https://token-plan-sgp.xiaomimimo.com/v1` |
| `KOLIBRI_V3_MIMO_MODEL` | Модель MiMo для чата | `mimo-v2.5-pro` |
| `KOLIBRI_V3_MIMO_CHAT_MODEL` | Модель MiMo для чата (override) | значение `KOLIBRI_V3_MIMO_MODEL` |
| `KOLIBRI_V3_MIMO_ESTIMATE_MODEL` | Модель MiMo для смет | значение `KOLIBRI_V3_MIMO_MODEL` |
| `KOLIBRI_V3_CODEX_MODEL` | Модель Codex CLI | `gpt-5.5` |
| `KOLIBRI_V3_CODEX_EFFORT` | Уровень reasoning Codex | `low` |
| `KOLIBRI_V3_DATABASE_URL` | URL SQLite базы | `sqlite:///./var/kolibri-v3.db` |
| `KOLIBRI_V3_ALLOWED_ORIGINS` | CORS origins | `http://127.0.0.1:3103,http://localhost:3103` |
| `MIMO_API_KEY` | API ключ MiMo | (обязательный) |
| `OPENAI_API_KEY` | API ключ OpenAI | (обязательный для Codex) |

См. полный список в `.env.example`.

## Проверки

```bash
npm run verify
npm run verify:full
```

Единые требования к TypeScript, Python, Rust, тестам и форматированию
зафиксированы в
[`docs/DEVELOPMENT_STANDARDS.md`](docs/DEVELOPMENT_STANDARDS.md).

## Production-деплой

Переносимый Linux/systemd-релиз, конфигурация одного изолированного инстанса,
атомарное переключение и локальный smoke-test описаны в
[`deploy/portable/README.md`](deploy/portable/README.md).

Подробный дизайн-контракт находится в
[`docs/DESIGN_PROJECT.md`](docs/DESIGN_PROJECT.md).
Канонические SSH-маршруты и порядок проверки физических Home/Primary
зафиксированы в
[`docs/INFRASTRUCTURE_ACCESS.md`](docs/INFRASTRUCTURE_ACCESS.md).
Границы owner-only очистки, защита активных данных и поэтапное включение
привилегированного node executor описаны в
[`docs/STORAGE_ADMIN_OPERATIONS.md`](docs/STORAGE_ADMIN_OPERATIONS.md).
Продуктовый backend-контракт — в
[`docs/PRODUCT_KERNEL_V1.md`](docs/PRODUCT_KERNEL_V1.md).
Разделение официальных, личных, коммерческих и будущих агрегированных цен
описано в [`docs/PRICING_MODEL.md`](docs/PRICING_MODEL.md).

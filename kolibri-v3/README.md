# Колибри V3

Новый chat-first продукт Kolibri. Web-интерфейс создан на официальных
примитивах `assistant-ui`, использует AG-UI как потоковый runtime и работает с
новым изолированным V3 backend. Старый `kolibri-backend` не является upstream
или fallback для этого приложения.

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

## Проверки

```bash
PYTHONPATH=backend backend/venv/bin/python -m pytest -q backend/tests
npm run typecheck
npm test
npm run build
```

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

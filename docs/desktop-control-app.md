# Desktop Control App MVP

Дата: 2026-06-29  
Инициатор: Владислав  
Роль спецификации: `desktop_control_app_mvp_architect`  
Статус: MVP specification для реализации на Ubuntu-фабрике.

## 1. Назначение

Desktop Control App - локальное desktop-приложение в стиле Codex, через
которое владелец управляет всей фабрикой Kolibri: ставит задачи, смотрит
состояние узлов, lease, артефакты, GitHub/CI, принимает review-решения и
видит деградации без ручного SSH.

Главное правило: приложение является control surface, а не отдельным
исполнителем. Источник факта по задачам, lease, node state и result references
остаётся в Control Plane. GitHub Project/PR/CI остаются внешним операционным
следом. Агентские worktree и artifacts остаются node-local.

## 2. Целевой пользователь

Основной пользователь MVP - Владислав как владелец и оператор фабрики.

Его ежедневные задачи:

- быстро понять, жива ли фабрика и где bottleneck;
- поставить новую задачу через проверенный task envelope;
- остановить, отменить или дренировать опасную работу;
- увидеть, кто держит lease, когда был heartbeat и какой следующий шаг;
- открыть результат, PR, CI, GitHub Project item и blocker report из одного
  места;
- получить честный degraded/offline статус, а не декоративный успех;
- работать в привычном chat-first интерфейсе, как в Codex.

Вторичный пользователь post-MVP - доверенный инженер-оператор с ограниченными
правами. В MVP допустим один owner-профиль.

## 3. Продуктовые принципы

- Chat-first: первый экран - рабочий чат-командный центр, а не dashboard.
- Codex-like UX: нижний composer, streaming/thinking state, история команд,
  правый нижний Control entry point, плотные панели без маркетингового слоя.
- Remote-first: все действия идут через Control Plane API и GitHub API/links;
  приложение не пишет напрямую в node-local файловые системы и не запускает
  ad hoc SSH.
- Проверяемость: любое действие оставляет task id, timestamp, actor, result
  reference или GitHub reference.
- Безопасность по умолчанию: секреты не попадают в prompt, envelope, logs,
  screenshots, PR comments и owner-facing summaries.
- Деградация честная: stale/cache/offline явно помечаются временем последнего
  успешного обновления.

## 4. Основные экраны MVP

### 4.1 Chat Command Center

Первый экран наследует текущий Kolibri/Codex-like чат:

- список сообщений и команд;
- bottom composer с multiline input;
- quick actions для "создать задачу", "статус фабрики", "показать blockers",
  "подготовить envelope";
- streaming ответ с фактами из Control Plane и GitHub;
- переключение между conversational mode и command mode;
- safe preview перед destructive action.

Команды из чата не выполняются скрыто. Для submit/cancel/drain нужен preview:
что будет отправлено, куда, каким actor и какой rollback/follow-up ожидается.

### 4.2 Factory Control Panel

Открывается из правой нижней кнопки `Control` и показывает:

- health Control Plane и Redis;
- queue length, states summary, stale lease/dead letter count;
- список nodes с hostname, node_id, capabilities, permissions,
  heartbeat age, active_task, draining;
- целевую нагрузку и резерв: 80% рабочая мощность, 20% emergency reserve;
- быстрые фильтры `queued`, `running`, `waiting_review`, `failed`,
  `dead_letter`, `cancelled`.

### 4.3 Task Composer / Envelope Builder

Экран для создания задач через envelope:

- выбор шаблона: generic implementation, QA, docs, GitHub/CI, factory SRE;
- обязательные поля: `task_id`, `kind`, `goal`, `acceptance`, `source`;
- дополнительные поля: `required_capability`, `permission_pack`, `runner`,
  `branch`, `base_ref`, `role_slot`, `role_goal`, `verification_commands`,
  `target_node` или `allowed_nodes`;
- JSON preview и встроенная проверка parse/required fields;
- submit через `POST /v1/tasks`;
- idempotency warning при повторной отправке.

### 4.4 Task Detail / Timeline

Экран одной задачи:

- state, attempt, attempt_id, lease_owner, lease_until, heartbeat_at;
- worktree/log/result references без раскрытия лишних локальных путей в
  owner-facing summary;
- acceptance checklist;
- agent messages по task_id;
- result и artifact-manifest references;
- кнопки: annotate, cancel, open PR, open GitHub issue, copy safe summary.

### 4.5 Nodes / Capacity

Операторский экран:

- поиск и фильтр по node_id, hostname, capability, health, draining;
- drain/undrain с обязательным подтверждением;
- active task и lease age;
- предупреждения о stale heartbeat, stale active_task, перегрузе и отсутствии
  permission pack;
- read-only machine stats: cpu, ram, disk.

### 4.6 Artifacts / Review

Экран проверки результата:

- result.json summary;
- artifact-manifest entries с checksum/size;
- PR URL, branch, commit, CI conclusion;
- reviewer decision: ready for review, needs follow-up, blocked;
- безопасный copy для GitHub comment без секретов и приватных путей.

### 4.7 GitHub / CI / Project

Экран внешнего операционного следа:

- PR/issue list, связанные с task_id;
- CI checks и вывод: green, red, pending, cancelled;
- GitHub Project fields: `Статус`, `Приоритет`, `Направление`, `Агент`,
  `Следующий отчёт`, `Артефакты`;
- fallback `Project sync: pending`, если OAuth scope недоступен;
- открытие GitHub в браузере без хранения лишних токенов в логах.

### 4.8 Settings / Security / Diagnostics

- Control Plane URL, backend URL, GitHub repo/project;
- auth status без показа токенов;
- local vault/keychain status;
- redaction test;
- export diagnostic bundle без секретов;
- offline queue review;
- app version, build hash, update channel.

## 5. UI/UX наследование от текущего Codex-like чата

MVP должен развивать текущий интерфейс Kolibri, а не заменять его отдельной
админкой:

- `/app` остаётся главным chat workspace;
- `Control` остаётся правым нижним entry point;
- панели тихие, плотные, пригодные для многократной работы;
- русский язык по умолчанию;
- статусы формулируются фактами: "heartbeat 12s ago", "CI failed",
  "Project sync pending";
- destructive actions требуют явного подтверждения с текстом действия;
- keyboard-first: focus composer, command palette, escape closes panel,
  searchable lists;
- accessibility: aria labels, focus states, reduced motion, contrast;
- mobile/PWA layout не ломается, но desktop app является основным MVP target.

## 6. Control Plane API

### 6.1 Текущие поддерживаемые контракты

MVP обязан использовать уже реализованные endpoints:

| Метод | Endpoint | Использование в desktop app |
| --- | --- | --- |
| `GET` | `/health` или `/v1/health` | Health Control Plane/Redis |
| `GET` | `/v1/nodes` | Nodes, heartbeat, drain, capabilities |
| `POST` | `/v1/nodes/<node_id>/drain` | Drain/undrain узла |
| `GET` | `/v1/tasks?summary=1&compact=1` | Сводка очереди |
| `GET` | `/v1/tasks?state=<state>&limit=<n>` | Фильтр задач |
| `GET` | `/v1/tasks/<task_id>` | Детали задачи |
| `POST` | `/v1/tasks` | Создание task envelope |
| `POST` | `/v1/tasks/<task_id>/cancel` | Отмена задачи |
| `POST` | `/v1/tasks/<task_id>/annotate` | Operator note/result annotation |
| `GET` | `/v1/agent-messages?target=all&limit=<n>` | Общая лента агентов |
| `POST` | `/v1/agent-messages` | Operator/status message |

Worker-only endpoints (`/v1/tasks/lease`, task heartbeat, complete, fail) в MVP
не должны вызываться desktop-приложением как обычные owner actions. Они
показываются в UI как lifecycle context, но выполняются Agent Host.

### 6.2 Целевые контракты для roadmap

Эти контракты допустимо показывать как planned/degraded, но нельзя делать
обязательной зависимостью MVP, пока backend не реализован:

- `GET /v1/filesystem` - namespace/manifest metadata, без чтения node-local
  файлов Control Plane;
- `GET /v1/tasks/<task_id>/artifacts` - безопасный список artifacts;
- `POST /v1/tasks/<task_id>/requeue` - явный owner requeue;
- `GET /v1/events` или WebSocket/SSE - live updates вместо polling;
- отдельный auth/audit endpoint для desktop sessions.

## 7. Безопасность

MVP security baseline:

- single owner session, token хранится в OS keychain/secret storage или в
  зашифрованном local profile; в логах токен всегда redacted;
- Control Plane доступен только через доверенную mesh/VPN-сеть или
  защищённый reverse proxy;
- destructive actions: cancel, drain, undrain, submit high-permission task -
  только после preview и confirmation;
- envelope linter запрещает секреты, `.env`, private keys, cookies, auth cache,
  персональные контакты инвесторов и приватные URLs;
- owner-facing summaries не раскрывают local artifact paths, node-local
  worktree paths и полные логи без явного раскрытия;
- audit trail: actor, action, task_id/node_id, timestamp, request id,
  sanitized payload hash;
- app build должен иметь checksum и воспроизводимую версию;
- GitHub token scopes минимальны; при отсутствии Project scope показывается
  blocker, а не fake success.

## 8. Offline / Degraded Mode

Состояния:

- `online`: Control Plane и GitHub доступны, polling/live updates работают;
- `control-plane-degraded`: health/tasks/nodes недоступны частично;
- `github-degraded`: GitHub/Project/CI недоступны, Control Plane работает;
- `offline`: сеть недоступна или app не может достучаться до всех upstream;
- `stale-cache`: показываются последние данные с timestamp.

Поведение MVP:

- cached factory snapshot read-only, с явным временем последнего обновления;
- draft envelopes сохраняются локально, но не auto-submit после reconnect;
- queued destructive actions требуют повторного подтверждения после reconnect;
- чат может работать как локальный command notebook, но ответы помечаются как
  not verified if upstream unavailable;
- GitHub операции пишутся как `Project sync: pending`;
- app не скрывает, что status устарел.

## 9. GitHub / CI / Project integration

MVP должен соединять Control Plane task state с GitHub-visible trail:

- task detail показывает PR/issue/result links из result payload;
- PR screen показывает checks и red/yellow blockers;
- Project status маппится по регламенту `docs/agent-work/github-project-ops.md`;
- если GitHub auth отсутствует, app открывает web links и фиксирует blocker;
- CI failure не считается завершением: нужен blocker report или follow-up;
- issue/PR/comment templates на русском и без секретов.

## 10. Ubuntu QA

Первичная целевая платформа для factory implementation и ручной проверки:

- Ubuntu 22.04 LTS и/или Ubuntu 24.04 LTS;
- Wayland и X11 smoke, если desktop wrapper поддерживает оба режима;
- запуск без root;
- network через mesh/VPN до `http://10.99.0.2:9101` или настроенный
  `KOLIBRI_CONTROL_URL`;
- проверка app package: AppImage или deb, плюс dev mode fallback;
- отсутствие секретов в `journalctl`, app logs, screenshots и artifacts.

Минимальные команды проверки implementation PR:

```bash
npm --prefix frontend run lint --if-present
npm --prefix frontend run build
npm --prefix frontend run test:mobile-layout --if-present
npm --prefix frontend run build:desktop --if-present
npm --prefix frontend run package:linux --if-present
python3 -m compileall -q backend ops tests
python3 -m pytest backend/tests tests
python3 -m json.tool ops/envelopes/KOL-DESKTOP-CONTROL-APP-MVP-20260629.json >/dev/null
```

## 11. Acceptance Criteria

MVP считается готовым, если:

- desktop app запускается на Ubuntu и открывается в chat-first режиме;
- Control Panel показывает health, nodes, task summary и degraded state;
- Task Composer создаёт валидный envelope и отправляет его через `/v1/tasks`;
- Task Detail показывает lifecycle, lease, heartbeat, messages и result
  references;
- cancel и drain/undrain требуют confirmation и отражаются в Control Plane;
- GitHub/CI/Project links или authenticated данные видны рядом с task;
- offline/degraded mode не выдаёт stale data за live state;
- security redaction покрывает tokens, env files, private keys, cookies,
  local paths in owner summaries;
- Ubuntu QA evidence приложен к PR/result artifact;
- документация и task envelope обновлены.

## 12. Roadmap

### M0 - Specification

- Зафиксировать этот документ.
- Подготовить implementation work package и Control Plane envelope.

### M1 - Read-only Desktop Console

- Desktop shell вокруг существующего React/Vite app.
- Health, nodes, tasks, task detail, agent feed.
- Cached snapshot и degraded labels.

### M2 - Controlled Actions

- Envelope builder и submit.
- Cancel task.
- Drain/undrain node.
- Annotate task/result.
- Audit trail и confirmation flows.

### M3 - GitHub / CI / Project

- PR/issue/checks view.
- Project status mapping.
- `Project sync: pending` fallback.
- Safe GitHub comment/update templates.

### M4 - Ubuntu Release Candidate

- AppImage или deb package.
- Ubuntu 22.04/24.04 QA.
- Smoke scripts, screenshots, sanitized logs.
- Owner handoff guide.

### Post-MVP

- Multi-user RBAC.
- Live event stream.
- Filesystem namespace manifests.
- Requeue/retry/dead-letter operator actions.
- Signed update channel.
- Mobile companion mode.

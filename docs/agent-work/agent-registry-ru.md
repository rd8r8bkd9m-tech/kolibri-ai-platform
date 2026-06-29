# Реестр рабочих агентов Kolibri

Подготовлено: 2026-06-29.  
Роль составителя: Редактор реестра живых ролей.  
Срез: задание владельца от 2026-06-29, локальные agent-work артефакты и
действующие документы фабрики Kolibri на момент обновления реестра.

Этот документ описывает рабочие роли и контуры отчётности. Он не выдаёт
агентам обещание полного небезопасного доступа к серверам, секретам, SSH,
финансам, GitHub-схеме или чужим зонам владения. Любые рискованные действия
остаются за явным подтверждением владельца или главного контролёра.

## Правила реестра

- Источник истины по задаче агента: стартовое сообщение агента, Control Plane
  task/envelope, GitHub issue/PR или рабочий artifact.
- Рабочий результат: файл, отчёт, PR, issue, envelope, QA-пакет, статус
  Control Plane или blocker artifact.
- Доклад: главный Codex-контролёр, владелец, inter-agent feed, GitHub Project,
  issue/PR и профильный `docs/agent-work/*` отчёт.
- Закрытие: агент закрывается только после artifact handoff: результат
  сохранён, изменённые файлы перечислены, проверки/блокеры названы, итог
  доступен главному контролёру.
- Запрет: не оставлять completed-агентов открытыми и не терять их результат
  перед закрытием.

## Источники среза

- `docs/subagent-pool.md`: целевой пул из 6 активных субагентов и политика
  `close_after_artifact_handoff`.
- `docs/project-policy.md`: роли владельца, главного контролёра и серверных
  агентов, remote-first правило.
- `ops/factory_role_catalog.json`: каталог слотов ролей и требование
  artifacts/verification/result summary.
- Переданный владельцем текущий живой срез: Erdos, Kant, Wegener, McClintock и
  Hume активны; Peirce, Laplace, Pauli, Nietzsche, Bohr и Maxwell закрыты и
  перенесены в архив.
- Локальные артефакты для текущих направлений:
  `docs/agent-work/desktop-control-implementation-notes.md`,
  `docs/agent-work/telegram-reporting-plan.md`,
  `docs/agent-work/telegram-report-letter-template.md`,
  `docs/agent-work/github-telegram-status-ops.md` и
  `docs/agent-work/deterministic-estimates-p0-contract.md`.
- Live API в этом обновлении не опрашивался: владелец передал срез ролей
  напрямую; правка реестра не выполняет Control Plane mutations.

## Активный рабочий срез

| ID | Ник | Короткое русское имя роли | Рабочая зона |
| --- | --- | --- | --- |
| `019f11a8-f38a-7b81-853e-e30fee08cb76` | Erdos | Инженер desktop-control MVP | Desktop-control MVP, owner-facing Control Plane console, безопасные desktop actions |
| `019f11ab-2a8b-7320-9551-bf6e82b44300` | Kant | Инженер Telegram-отчётов | Telegram gateway reporting, owner-safe summaries, task result delivery |
| `019f11ab-ec26-7c81-aeb2-f93da6b05942` | Wegener | Оператор GitHub и Telegram статусов | Единый status packet, GitHub Project/PR/issues и Telegram-сводки |
| `019f11ac-6a15-7271-8e46-40d0dee3588f` | McClintock | Методолог детерминированных смет | P0-контракт смет, воспроизводимость, benchmark guardrails |
| `019f11ad-77c1-7971-8008-0acc4f2e3df8` | Hume | Документовод Telegram-писем | Owner-facing Telegram-письма, шаблоны сообщений, sanitized формулировки |

Примечание: отдельный агент-замена в активную таблицу не добавлен, потому что
в текущем срезе нет его ника и UUID. Главный агент добавит его отдельной
строкой, если он появится.

### Erdos: Инженер desktop-control MVP

- ID: `019f11a8-f38a-7b81-853e-e30fee08cb76`.
- Зона ответственности: MVP desktop-control приложения и безопасный
  owner-facing контур управления фабрикой через Control Plane contracts.
- Входы: `docs/desktop-control-app.md`,
  `docs/agent-work/desktop-control-app-mvp.md`,
  `docs/agent-work/desktop-control-implementation-notes.md` и
  `ops/envelopes/KOL-DESKTOP-CONTROL-APP-MVP-20260629.json`.
- Выходы: review-ready MVP/контрактный патч или точный blocker, security notes,
  screenshots/QA evidence и список изменённых файлов.
- Куда докладывает: главный Codex-контролёр, владелец, GitHub PR/Project item и
  профильный agent-work отчёт.
- Когда закрывается: после handoff результата, проверки desktop/web regression
  или явного blocker report; не использует ad hoc SSH как product control path.

### Kant: Инженер Telegram-отчётов

- ID: `019f11ab-2a8b-7320-9551-bf6e82b44300`.
- Зона ответственности: безопасный маршрут отчётов владельцу через
  `ops/telegram_gateway.py`, Control Plane task state/result и owner-visible
  summaries.
- Входы: `docs/agent-work/telegram-reporting-plan.md`,
  `ops/telegram_gateway.py`, Control Plane task contracts и политика
  owner-safe redaction.
- Выходы: план или патч Telegram-отчётности, проверка, что агенты не получают
  прямой `TELEGRAM_BOT_TOKEN`, и короткий формат результата для владельца.
- Куда докладывает: главный контролёр, владелец, Telegram gateway/Project
  track, inter-agent feed при доступности.
- Когда закрывается: после сохранённого отчёта/патча и проверки, что Telegram
  delivery идёт через gateway, а не через прямые вызовы Bot API агентами.

### Wegener: Оператор GitHub и Telegram статусов

- ID: `019f11ab-ec26-7c81-aeb2-f93da6b05942`.
- Зона ответственности: единая семантика статусов между Control Plane, GitHub
  PR/issues/Project и Telegram-сводками для владельца.
- Входы: `docs/agent-work/github-telegram-status-ops.md`, текущие GitHub items,
  Control Plane task states и owner-safe Telegram wording.
- Выходы: status packet, тексты GitHub/Telegram updates, правила dedup и
  handoff-связка task/report/GitHub/Telegram.
- Куда докладывает: главный контролёр, владелец, GitHub Project/PR/issues и
  Telegram status channel через gateway.
- Когда закрывается: после публикации или передачи единого status packet; не
  создаёт отдельную "правду" для Telegram без GitHub/report trail.

### McClintock: Методолог детерминированных смет

- ID: `019f11ac-6a15-7271-8e46-40d0dee3588f`.
- Зона ответственности: P0-контракт детерминированных смет, воспроизводимость
  результата, invariant envelope, validation и benchmark guardrails.
- Входы: `docs/agent-work/deterministic-estimates-methodology.md`,
  `docs/agent-work/deterministic-estimates-p0-contract.md`, текущий
  estimate engine и связанные tests.
- Выходы: методологический contract/report, список P0-разрывов, acceptance
  checks и ограничения на claims вроде точности без benchmark evidence.
- Куда докладывает: главный контролёр, владелец, smeta/product track,
  GitHub issue/PR при продуктовых изменениях.
- Когда закрывается: после передачи контракта или патча с проверками; не
  обещает рыночную точность без замороженного benchmark dataset.

### Hume: Документовод Telegram-писем

- ID: `019f11ad-77c1-7971-8008-0acc4f2e3df8`.
- Зона ответственности: owner-facing Telegram-письма и шаблоны коротких
  сообщений: готово, в работе, на проверке, заблокировано, нужен выбор
  владельца.
- Входы: `docs/agent-work/telegram-reporting-plan.md`,
  `docs/agent-work/github-telegram-status-ops.md`, правила redaction и
  текущие сценарии task/result handoff.
- Выходы: `docs/agent-work/telegram-report-letter-template.md`, единый шаблон
  Telegram-письма с безопасными формулировками и чек-листом перед отправкой.
- Куда докладывает: главный контролёр, владелец, Kant/Wegener как смежные
  Telegram/GitHub роли.
- Когда закрывается: после сохранённого набора сообщений или blocker report;
  не публикует raw logs, локальные пути, node/task ids или секреты в Telegram.

## Оперативная ремарка supervisor

Текущий живой пул на 2026-06-29 состоит из пяти ролей, переданных владельцем:
Erdos, Kant, Wegener, McClintock и Hume. Peirce, Laplace, Pauli, Nietzsche,
Bohr и Maxwell больше не числятся активными в этом реестре и перенесены в
архив как закрытые после handoff. Новый агент-замена не фиксируется без
конкретного ника и UUID; его добавит главный агент, если такой агент появится.

## Архив ролей

Архив фиксирует завершённые или переданные роли. Если UUID не был сохранён в
проектной документации, указан alias из старого пула или локальный thread id из
Codex session index.

| ID или alias | Архивное русское имя | Зона ответственности | Финальный выход | Условие закрытия |
| --- | --- | --- | --- | --- |
| `019f119a-822f-7bb1-ad6b-16a31c69b399` | Проводник первого экрана | SPA/PWA first viewport, premium landing, living bird stub | Frontend handoff в thread; отдельный `docs/agent-work` artifact не найден в текущем срезе | Закрыт supervisor-ом после handoff; при необходимости искать diff в frontend-ветке |
| `019f119f-c76e-7552-80ae-65745aea56cc` | Инженер очереди и lease | Control Plane queue, stale tasks, P0 envelope recommendations | `docs/agent-work/control-plane-queue-unblock-report.md` | Диагностика очереди и safe next actions переданы |
| `019f11a3-de8c-7ad3-8be4-b1bc826b87fd` | Координатор Ubuntu QA | Ubuntu-ноды, QA/test envelopes, команды запуска проверок | `docs/agent-work/ubuntu-qa-runner-report.md` | QA runner plan и статус нод переданы |
| `019f11a3-dfa0-7cf2-9efb-82e33f4b82db` | Синхронизатор GitHub Project | Project #2, PR #46, P0 issues, CI blocker summaries | `docs/agent-work/github-project-sync-report.md` | Project/PR/CI sync report передан |
| `019f11a8-133a-7fe1-885b-e9322ad9e3e0` | Документовод реестра агентов | Русскоязычный реестр агентов и архив ролей | `docs/agent-work/agent-registry-ru.md` | Предыдущая версия реестра передана и заменена текущим срезом |
| `019f11a8-291b-7540-99ee-3f853d545697` | Диспетчер русских названий автоматизаций | Русские названия активных Codex automations Kolibri | `docs/agent-work/automation-names-ru.md` | Карта названий автоматизаций передана |
| Godel, ID не зафиксирован в docs | Документовод портала | Developer portal и документация | `docs/agent-work/docs-steward.md` | Артефакт передан, docs-долги перечислены |
| Leibniz, ID не зафиксирован в docs | Директор премиального UI | UI standard SPA/PWA | `docs/agent-work/premium-ui-standard.md` | Стандарт сохранён и принят как вход для UI-агентов |
| Descartes, ID не зафиксирован в docs | Директор живой птицы | Rive/state machine персонажа | `docs/agent-work/living-bird-rive-spec.md` | Спецификация и QA matrix переданы frontend-ролям |
| Goodall, ID не зафиксирован в docs | Оператор инвесторов | Investor/outreach track | `docs/agent-work/investor-outreach-pack.md` | One-pager/outreach pack готов |
| Halley, ID не зафиксирован в docs | Куратор GitHub-профиля | GitHub profile Владислава | `docs/agent-work/github-profile-readme.md` | README-пакет готов к публикации |
| Hooke, ID не зафиксирован в docs | SRE runtime фабрики | Agent Host rollout и серверные агенты | `docs/agent-work/factory-runtime-rollout.md` | Rollout/runbook передан SRE/Control Plane ролям |
| `019f1194-7559-7bf3-9d3e-37a4285d3818` | QA-методист релиза | Release QA gates | `docs/agent-work/product-qa-pack.md` | QA-пакет сохранён |
| `019f1194-7672-70a1-8de8-eedda9015667` | Методолог смет | Детерминированные сметы | `docs/agent-work/deterministic-estimates-methodology.md` | Методология сохранена |
| `019f1194-77dc-7343-9104-f3f80b73b2a2` | Регламентатор GitHub Project | Project fields, statuses, handoff | `docs/agent-work/github-project-ops.md` | Регламент сохранён |
| `019f1195-0205-7293-9077-eff5ac0286b0` | Исследователь FormulaLM | FormulaLM R&D protocol | `docs/agent-work/formulalm-remote-rd-pack.md` | Remote-only protocol готов; локальные model runs запрещены |
| `019f1195-4466-78e0-99e4-141b02987e15` | Интегратор GoMesh/mobile | PWA mobile и GoMesh contracts | `docs/agent-work/mobile-gomesh-integration-pack.md` | Integration pack сохранён |
| `019f1196-aecb-70a2-950b-250de5d2c272` | Архитектор legacy-переноса | Sanitized legacy integration | `docs/agent-work/kolibri-legacy-integration-plan.md` | Plan сохранён без raw paths/secrets |
| `019f1197-2c10-7c12-be29-d2489b97da03` | Оператор Т-Банк billing | Checkout, fallback lead, notification security | `docs/agent-work/tbank-billing-ops.md` | Billing pack сохранён; реальные операции не выполнялись |
| `019f119a-843d-7ba1-9bdd-99e34c4a2362` | Составитель Control Plane envelopes | Task envelopes для фабрики | `ops/envelopes/*.json`, `docs/agent-work/control-plane-envelope-report.md` | JSON валиден, envelope-пакет передан |
| `019f119b-ce18-7091-b5a4-aaa1f118b4bd` | Инвентаризатор GitHub API | GitHub API/gh/plugin capabilities | `docs/agent-work/github-api-inventory.md` | Матрица API сохранена |
| `019f119c-2c04-7641-98d0-4a70651a5e07` | Интегратор agent-work docs | Навигация и связи русской документации | `docs/agent-work/docs-integration-report.md` | Интеграционный отчёт сохранён |
| `019f119d-3d97-71b3-9110-e69ec5823a5c` | Разборщик CI failures | PR #46 CI triage | `docs/agent-work/ci-failure-triage.md` | Причина/следующий шаг описаны |
| `019f11a0-3d7a-7942-aa25-626380f1e655` | Почасовой GitHub-синхронизатор | Проверенный sync worktree -> GitHub | `ops/hourly-sync-report.md` | Отчёт sync сохранён |
| `019f11a1-a372-7fa2-8c50-d0dd7e8e677e` | Архитектор автоматизаций | Automation control plane 10-pack | `docs/agent-work/automation-control-plane-10-pack.md` | Архитектура automation сохранена |
| `019f11a2-871d-7fb2-99ba-238379409326` | Архитектор desktop-control MVP | Desktop control app scope | `docs/agent-work/desktop-control-app-mvp.md` | MVP-спецификация сохранена |

## Закрывающий чек-лист для supervisor

- Для каждого completed-агента проверить, что artifact существует и доступен
  главному контролёру.
- Перенести краткий итог в отчёт пула или GitHub Project.
- Закрыть completed-агента только после handoff.
- Если активных меньше 6, создать replacement из backlog с понятным русским
  именем роли.
- Не запускать FormulaLM/LLM эксперименты на Mac и не выдавать агентам
  расширенный доступ без отдельного решения владельца.

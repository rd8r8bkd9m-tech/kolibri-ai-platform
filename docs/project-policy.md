# Политика разработки Kolibri AI Platform

Этот документ — единая политика проекта. Он фиксирует, как мы разрабатываем
приложение, фабрику, агентов, документацию, дизайн, FormulaLM, инвесторский
трек и GitHub-процессы.

Главное правило: мы создаём искусственный интеллект. Любое решение должно
усиливать автономную AI-платформу, а не превращать проект в набор ручных
скриптов.

## 1. Северная звезда

Kolibri AI Platform должна стать AI-фабрикой венчурного масштаба:

- стоимость цели — многомиллиардный продукт;
- первый коммерческий wedge — детерминированные строительные сметы;
- ядро — Control Plane, агентная фабрика, FormulaLM, SPA/PWA и GitHub Project;
- продукт продаётся через подписки, пилоты, enterprise-интеграции и
  стратегические партнёрства;
- всё, что можно автоматизировать, автоматизируется через серверных агентов.

## 2. Роли человека и агентов

Владелец:

- ставит цели через Telegram, чат или Codex;
- смотрит статус в GitHub Project, PR, issue и отчётах;
- принимает стратегические решения и даёт недостающие данные.

Главный Codex-контролёр:

- проверяет результаты, интегрирует изменения, запускает тесты;
- не выполняет тяжёлые эксперименты на Mac;
- создаёт и проверяет task envelopes;
- держит целевой пул из 6 активных субагентов;
- закрывает завершённых субагентов после передачи артефактов;
- поднимает нового субагента сразу после закрытия завершённого, чтобы пул
  снова был равен 6;
- фиксирует политику, документацию и блокеры.

Серверные агенты:

- получают задачи только через Control Plane;
- работают в node-local worktree;
- возвращают результат артефактами;
- докладывают статус через inter-agent API и GitHub;
- не печатают секреты и не используют ad hoc SSH как основной путь.

## 3. Remote-first правило

Mac используется только как пульт управления и редакторская поверхность.

Запрещено на Mac:

- запускать FormulaLM/Qwen/LLM benchmark;
- запускать `ollama`, `vllm`, training, fine-tuning и model inference;
- проводить нагрузочные тесты моделей;
- считать локальный результат доказательством качества FormulaLM.

Разрешено на Mac:

- читать и редактировать репозиторий;
- готовить envelopes;
- отправлять задачи через `ops/kolibri-dispatch submit --file`;
- собирать статусы через Control Plane;
- запускать лёгкие unit/contract tests для проверки кода.

## 4. Фабрика

Фабрика работает через Control Plane:

```mermaid
sequenceDiagram
    participant Owner as Владелец
    participant CP as Control Plane
    participant Agent as Серверный агент
    participant Feed as Inter-agent API
    participant GH as GitHub

    Owner->>CP: цель / задача
    CP->>Agent: lease
    Agent->>Feed: task_started
    Agent->>Agent: работа в node-local worktree
    Agent->>Feed: task_completed или task_failed
    Agent->>GH: branch / PR / issue / report
    CP->>Owner: статус и артефакты
```

Правила фабрики:

- целевая загрузка — 80%, резерв — 20%;
- новые серверы готовятся одинаковым golden bootstrap;
- масштабирование — пачками по 10 серверов, без ручной уникальной настройки;
- при 2000 новых серверов применяется тот же bootstrap и role catalog;
- stale-ноды не получают критические задачи, пока heartbeat/runtime не
  восстановлены;
- завершённые субагенты закрываются после сохранения результата;
- локальный supervisor `kolibri-subagent-pool-supervisor` проверяет пул каждые
  15 минут, закрывает completed-агентов и создаёт замену;
- каждый агент обязан оставить артефакт, даже если задача заблокирована.

## 5. Типы задач

Каждая задача должна иметь:

- `task_id`;
- `kind`;
- `required_capability`;
- `goal`;
- `role_slot`;
- `acceptance`;
- `verification_commands`;
- `source`;
- ожидаемые артефакты.

Нельзя отправлять расплывчатые задачи без критериев готовности.

## 6. GitHub

GitHub — главный внешний журнал разработки.

Обязательно:

- каждая значимая работа идёт через branch, commit, PR или issue;
- упавшие GitHub checks мониторятся и исправляются;
- PR содержит, что сделано, как проверено, риски и блокеры;
- агенты пишут отчёты на русском языке;
- GitHub Project является главным экраном мониторинга после расширения OAuth
  scope `project` и `read:project`.

Структура GitHub Project:

- `Статус`: `Новая`, `В работе`, `На проверке`, `Заблокирована`, `Готово`;
- `Приоритет`: `P0`, `P1`, `P2`;
- `Направление`: `Фабрика`, `SPA/PWA`, `FormulaLM`, `Сметы`, `Инвесторы`,
  `GitHub/CI`, `Документация`, `Живая птица`, `Мобильный слой`;
- `Агент`;
- `Следующий отчёт`;
- `Артефакты`.

Пока Project API заблокирован scope, агенты используют issues/PR comments.

## 7. Документация

Документация ведётся на русском языке и обновляется постоянно.

Обязательные разделы:

- обзор проекта;
- quickstart;
- API reference;
- запуск и деплой;
- Control Plane и Agent Host;
- task envelopes;
- inter-agent API;
- SPA/PWA;
- T-Банк и подписки;
- детерминированные сметы;
- FormulaLM;
- GoMesh/mobile;
- GitHub Project и CI;
- инвесторский трек;
- runbooks и incident reports.

Документовод:

- автоматически обходит проект;
- фиксирует новые API, env vars, команды и ограничения;
- готовит русские страницы, схемы Mermaid, runbooks, письма и one-pagers;
- создаёт GitHub issue/PR для документационных долгов;
- не ждёт ручного сбора материалов.

## 8. Продукт и дизайн

Приложение — SPA/PWA премиум-уровня.

Основные правила:

- рабочее приложение остаётся chat-first;
- вся вторичная работа через кнопку `Control` в правом нижнем углу;
- схема расширения — через плагины, как в Codex;
- светлая и системная тема обязательны;
- тёмная тема допустима, но не должна ломать премиум-ощущение;
- landing нужен отдельно от рабочего `/app`;
- дизайн должен быть дорогим, спокойным, точным, без дешёвых декоративных
  эффектов;
- компоненты переиспользуемые, не одноразовая вёрстка.

Проверки дизайна:

- desktop, tablet, mobile;
- safe areas iOS/Android;
- отсутствие overlap;
- читаемость длинных русских строк;
- installable PWA;
- keyboard/focus;
- empty/loading/error/success states.

## 9. Живая птица Kolibri

Птица — продуктовый персонаж, а не CSS-украшение.

Цель:

- реагировать на состояние приложения;
- жить в интерфейсе сама по себе;
- иметь характер для каждого клиента;
- усиливать доверие, не мешая работе.

Технический стандарт:

- основной путь — Rive state machine;
- state inputs: `mood`, `energy`, `attention`, `taskState`, `clientTrait`;
- fallback — PixiJS sprite/runtime или текущий SVG-компонент;
- Lottie используется только для линейных анимаций, не как главный мозг
  персонажа.

Состояния:

- `idle`;
- `listening`;
- `thinking`;
- `working`;
- `success`;
- `warning`;
- `error`;
- `offline`;
- `celebrating`;
- `sleepy`.

Персональность клиента:

- сохраняется в профиле;
- влияет на микродвижения, скорость, реакции и тон;
- не должна ухудшать доступность или производительность.

## 10. Сметы

Сметы должны быть детерминированными.

Если вводные одинаковые, регион одинаковый, прайсбук одинаковый и условия
одинаковые, результат должен совпадать.

Обязательные свойства:

- versioned pricebook;
- canonical input hash;
- deterministic estimate id;
- audit trail;
- редактируемость после генерации;
- отделение работ, материалов, накладных, налогов и итогов;
- честная метрика точности 98-99%, подтверждённая тестами.

## 11. FormulaLM

FormulaLM — отдельное R&D-направление.

Правила:

- эксперименты только на удалённых серверах;
- Mac не используется для модельных тестов;
- baseline и FormulaLM сравниваются на одном датасете;
- результаты не выдумываются;
- если runtime/model отсутствует, задача возвращает blocker artifact;
- raw logs не публикуются без проверки на секреты и приватные данные.

## 12. Инвесторы и клиенты

Проект должен быть готов к продаже клиентам и презентации инвесторам.

Обязательные артефакты:

- лендинг;
- one-pager RU/EN;
- pitch deck;
- demo script;
- investor CRM;
- список первых клиентов;
- письма outreach;
- proof-пакет по сметам;
- proof-пакет по фабрике;
- FormulaLM research note.

Агенты по инвесторам и продажам должны готовить документы и письма полностью,
а не только анализ.

## 13. Релизы и QA

Перед тем как отдавать результат владельцу:

- локальные unit/contract tests;
- frontend build;
- backend tests;
- factory contract tests;
- browser screenshots;
- mobile viewport checks;
- независимый QA task через Control Plane;
- проверка GitHub CI;
- список блокеров и nonblocking warnings.

Нельзя говорить “готово”, если есть P0-блокер.

## 14. Секреты и доступы

Запрещено:

- печатать токены;
- коммитить `.env`, auth files, tokens, private keys;
- отправлять секреты в task envelope;
- давать агентам доступ вне политики;
- обходить Control Plane ad hoc SSH как основной механизм.

Разрешено:

- использовать секреты только из безопасного окружения сервера;
- возвращать blocker, если секрета нет;
- логировать факт наличия/отсутствия секрета без значения.

## 15. Автоматизация

Автоматизации:

- hourly verified GitHub sync;
- GitHub CI auto-fix monitor;
- FormulaLM follow-up;
- documentation steward task;
- investor/outreach task;
- premium UI QA task;
- living character R&D task.

Каждая automation должна иметь понятную цель, проверку и артефакт.
Любая automation проходит один обязательный контур:
`analyze -> execute -> verify -> report`.

### 15.1 Машиночитаемая политика исполнения automation

```yaml
automation_execution_policy:
  id: kolibri_automation_execution_policy
  version: "2026-06-29"
  language: ru
  applies_to:
    - scheduled_automation
    - control_plane_task
    - agent_work_handoff
    - github_ci_auto_fix
    - documentation_steward
  required_flow:
    ordered_steps:
      - analyze
      - execute
      - verify
      - report
    rule_ru: "Automation не может завершиться после одного анализа."
  completion_gate:
    complete_requires_all:
      - analysis_recorded
      - execution_completed_or_handoff_submitted
      - verification_completed_or_blocker_recorded
      - report_published
      - owner_visible_status_updated
    analysis_only:
      terminal_status: false
      status_ru: "incomplete"
      allowed_only_with_execution_handoff: true
      handoff_requires_all:
        - control_plane_task_envelope_or_submission_pattern
        - execution_owner_or_required_capability
        - acceptance_criteria
        - required_evidence
        - verification_commands
        - result_reference_target
        - owner_visible_status_target
  required_evidence:
    changed_file_or_artifact:
      required: true
      examples:
        - "changed_files"
        - "docs/agent-work/<task>-result.md"
        - "artifact_dir/result.json"
    commands_or_checks:
      required: true
      examples:
        - "git diff --check"
        - "python -m pytest <focused-test>"
        - "python -m json.tool <envelope>.json"
    report:
      required: true
      examples:
        - "PR body"
        - "issue/comment"
        - "docs/agent-work/<task>-report.md"
        - "Control Plane result payload"
    owner_visible_status:
      required: true
      allowed_targets:
        - "GitHub Project"
        - "GitHub issue"
        - "GitHub PR"
        - "Control Plane result_reference"
        - "Telegram owner report"
  formula_lm_and_model_guard:
    mac_formula_lm_or_llm_experiments: forbidden
    allowed_on_mac:
      - "prepare_envelope"
      - "read_docs"
      - "light_unit_or_contract_tests"
      - "collect_remote_status"
    remote_required_for:
      - "FormulaLM"
      - "Qwen"
      - "LLM benchmark"
      - "model inference"
      - "training_or_fine_tuning"
  failure_policy:
    missing_evidence_status: blocked_or_incomplete
    fabricated_result: forbidden
    blocker_requires:
      - exact_reason
      - checks_attempted
      - next_required_owner_or_infra_action
      - result_reference
```

### 15.2 Execution handoff через Control Plane

Если automation выполнила только анализ, она обязана передать исполнение через
Control Plane. Минимальный handoff считается достаточным только если в нём есть
конкретная задача, критерии приёмки, ожидаемые доказательства и место, где
владелец увидит статус.

Шаблон task envelope:

```json
{
  "task_id": "KOL-EXECUTION-HANDOFF-YYYYMMDD",
  "kind": "remote_implementation",
  "required_capability": "generic_implementation",
  "role_slot": "autonomous_engineer",
  "goal": "Выполнить конкретное изменение из analysis artifact. Сначала прочитать source_doc, затем реализовать, проверить и опубликовать report. Не запускать FormulaLM/LLM/model experiments на Mac.",
  "source": {
    "source_doc": "docs/agent-work/<analysis-artifact>.md",
    "policy": "docs/project-policy.md#151-машиночитаемая-политика-исполнения-automation"
  },
  "acceptance": [
    "Есть изменённый файл или артефакт результата",
    "Есть список команд/проверок с результатами",
    "Есть report для owner/GitHub/Control Plane",
    "Owner-visible статус обновлён или указан точный blocker",
    "Если исполнение невозможно, возвращён blocker с result_reference и next action"
  ],
  "verification_commands": [
    "git diff --check",
    "python -m json.tool ops/envelopes/KOL-EXECUTION-HANDOFF-YYYYMMDD.json"
  ],
  "expected_evidence": {
    "changed_files": ["docs/agent-work/<result-artifact>.md"],
    "checks": ["<exact command>: <ok|failed|skipped with reason>"],
    "report": "docs/agent-work/<execution-report>.md",
    "owner_visible_status": "GitHub PR/comment, GitHub Project item или Control Plane result_reference"
  },
  "safety": {
    "no_secrets_in_output": true,
    "no_formula_lm_or_llm_on_mac": true,
    "control_plane_only": true
  }
}
```

Паттерн отправки:

```bash
python -m json.tool ops/envelopes/KOL-EXECUTION-HANDOFF-YYYYMMDD.json
ops/kolibri-dispatch submit \
  --file ops/envelopes/KOL-EXECUTION-HANDOFF-YYYYMMDD.json \
  --control-url "${KOLIBRI_FACTORY_CONTROL_URL:-http://10.99.0.2:9101}"
```

## 16. Блокеры

Если агент не может продолжать:

- фиксирует точный блокер;
- пишет, что проверил;
- пишет, что нужно от владельца или инфраструктуры;
- не выдумывает результат;
- оставляет issue/PR/comment или Control Plane artifact.

## 17. Политика памяти

Все важные решения фиксируются в репозитории:

- политика — `docs/project-policy.md`;
- API — `docs/api.md`;
- фабрика — `docs/factory.md`;
- GitHub — `docs/github-ci.md`;
- инвесторы — `docs/investors.md`;
- FormulaLM — `docs/formulalm.md`;
- мобильный слой — `docs/mobile-gomesh.md`.

Если решение не записано, оно считается риском забывания и должно быть
добавлено в документацию.

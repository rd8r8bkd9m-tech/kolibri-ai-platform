# Отчёт интеграции agent-work пакетов в русскую документацию

Дата: 2026-06-29.

Роль: `russian_docs_integrator`.

## Область

Обновлены только документы из зоны владения:

- `docs/README.md`;
- `docs/github-ci.md`;
- `docs/investors.md`;
- `docs/living-bird.md`;
- `docs/formulalm.md`;
- `docs/subagent-pool.md`;
- `docs/agent-work/docs-integration-report.md`.

Код, backend, frontend, ops и соседние документы вне зоны владения не
изменялись.

## Интегрированные пакеты

| Пакет | Статус интеграции | Куда вынесена короткая навигация |
| --- | --- | --- |
| `docs/agent-work/formulalm-remote-rd-pack.md` | Интегрирован | `docs/README.md`, `docs/formulalm.md`, `docs/github-ci.md`, `docs/subagent-pool.md` |
| `docs/agent-work/product-qa-pack.md` | Интегрирован | `docs/README.md`, `docs/github-ci.md`, `docs/living-bird.md`, `docs/subagent-pool.md` |
| `docs/agent-work/github-project-ops.md` | Интегрирован | `docs/README.md`, `docs/github-ci.md`, `docs/subagent-pool.md` |
| `docs/agent-work/tbank-billing-ops.md` | Интегрирован | `docs/README.md`, `docs/investors.md`, `docs/github-ci.md`, `docs/subagent-pool.md` |
| `docs/agent-work/mobile-gomesh-integration-pack.md` | Интегрирован через навигацию и роли | `docs/README.md`, `docs/github-ci.md`, `docs/subagent-pool.md` |
| `docs/agent-work/kolibri-legacy-integration-plan.md` | Интегрирован | `docs/README.md`, `docs/formulalm.md`, `docs/github-ci.md`, `docs/subagent-pool.md` |
| `docs/agent-work/living-bird-rive-spec.md` | Интегрирован | `docs/README.md`, `docs/living-bird.md`, `docs/subagent-pool.md` |
| `docs/agent-work/investor-outreach-pack.md` | Интегрирован | `docs/README.md`, `docs/investors.md`, `docs/subagent-pool.md` |

## GitHub Project API correction

Устаревшая формулировка про blocker создания GitHub Project снята в
`docs/github-ci.md`.

Актуальный статус:

- GitHub Project создан:
  `https://github.com/users/rd8r8bkd9m-tech/projects/2`;
- owner: `rd8r8bkd9m-tech`;
- project number: `2`;
- `gh` scopes: `repo`, `workflow`, `project`, `user`, `read:org`, `gist`.

Если будущая команда `gh project` падает, это нужно оформлять как новый точный
blocker конкретной операции, а не как старый blocker создания проекта.

## GitHub API inventory

Отдельный пакет `GitHub API inventory` в `docs/agent-work/` не найден.
Проверялся список Markdown-файлов и поиск по `inventory`/`GitHub API`.

До появления inventory источниками являются:

- `docs/github-ci.md`;
- `docs/agent-work/github-project-ops.md`.

После появления inventory его нужно добавить в:

- таблицу `Agent-work пакеты` в `docs/README.md`;
- раздел `GitHub API inventory` в `docs/github-ci.md`;
- этот отчёт.

## Что изменено по смыслу

- FormulaLM описан как remote-only R&D с гипотезами, метриками, preflight,
  blocker artifacts и GitHub-ready отчётом.
- Product QA стал обязательной release рамкой для SPA/PWA, backend, billing,
  factory, GitHub Project, mobile/GoMesh и living bird.
- T-Банк вынесен в investor evidence как operational billing path, но с
  честным production-readiness gate через sandbox/prod QA.
- Mobile/GoMesh зафиксирован как PWA-first стратегия и контрактная интеграция
  без принятия владения GoMesh-кодом.
- Legacy integration описан как sanitized перенос идей в текущие contracts,
  без raw legacy paths, секретов и недоказанных claims.
- Living bird получил ссылку на Rive spec, expanded states, fallback contract и
  QA checks.
- Пул субагентов получил роли для FormulaLM, QA, GitHub Project, T-Банк,
  GoMesh, legacy integration и русской документации.

## Проверка

Рекомендуемая проверка после правок:

```bash
git status --short docs/README.md docs/github-ci.md docs/investors.md docs/living-bird.md docs/formulalm.md docs/subagent-pool.md docs/agent-work/docs-integration-report.md
rg -n "projects/2|repo.*workflow.*project|GitHub API inventory|FormulaLM Remote|T-Банк billing|Mobile/GoMesh|Legacy Integration" docs/README.md docs/github-ci.md docs/investors.md docs/living-bird.md docs/formulalm.md docs/subagent-pool.md docs/agent-work/docs-integration-report.md
```

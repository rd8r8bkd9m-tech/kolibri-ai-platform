# Server-kfrm submission guard

Дата: 2026-06-29  
Роль: `server_kfrm_submission_guard_executor`  
Scope: создать read-only guard перед возможным submit server-kfrm recovery
envelope.

В рамках этой работы live mutation не выполнялась: не было submit, SSH, SCP,
drain/restart/bootstrap, stage/commit/push, FormulaLM или LLM workloads на Mac.

## Артефакт

Скрипт: `scripts/server_kfrm_submission_guard.sh`

Назначение: перед operator-approved submit проверить, что локальные envelopes
валидны, Control Plane доступен только через read-only GET, существующий probe
`KOL-SERVER-KFRM-PROBE-20260629` не дублируется, а команда submit recovery
envelope печатается только если guard не нашел блокеров.

Скрипт не вызывает `submit`, `cancel`, `drain`, `retry`, `ssh`, `scp`,
bootstrap/restart или workload-команды. Единственные live обращения: read-only
`GET /health`, `GET /v1/nodes`, `GET /v1/tasks/KOL-SERVER-KFRM-PROBE-20260629`.

## Проверки

Локальные JSON gates:

- `ops/envelopes/KOL-SERVER-KFRM-RUNTIME-RECOVERY-20260629.json` существует и
  проходит `python3 -m json.tool`;
- recovery envelope содержит `task_id`, `idempotency_key` и явный guardrail
  `Do not run FormulaLM`;
- `ops/envelopes/KOL-SERVER-KFRM-PROBE-20260629.json` существует и проходит
  `python3 -m json.tool`;
- probe envelope имеет `task_id=KOL-SERVER-KFRM-PROBE-20260629`;
- probe idempotency key равен
  `server-kfrm:read-only-probe:2026-06-29`;
- probe target равен `server-kfrm`;
- probe kind равен `read_only_probe`.

Read-only Control Plane gates:

- `/health` отвечает HTTP 200 и `status=ok`;
- `/v1/nodes` читается;
- executor card `server-kfrm` существует отдельно от `mesh-server-kfrm`;
- виден fresh executor с capability `generic_implementation` для
  orchestration-задачи;
- targeted probe читается через `/v1/tasks/KOL-SERVER-KFRM-PROBE-20260629`;
- существующий probe находится в понятном состоянии:
  `queued`, `leased`, `running`, `completed`, `failed`, `cancelled` или
  `dead_letter`;
- live probe idempotency key, если Control Plane его возвращает, совпадает с
  ожидаемым.

Если probe отсутствует, guard блокирует recovery submit и просит отдельное
operator decision на создание probe. Это предотвращает скрытый duplicate submit.

## Использование

```bash
bash -n scripts/server_kfrm_submission_guard.sh

KOLIBRI_FACTORY_CONTROL_URL="http://10.99.0.2:9101" \
  scripts/server_kfrm_submission_guard.sh
```

По умолчанию guard проверяет:

```text
ops/envelopes/KOL-SERVER-KFRM-RUNTIME-RECOVERY-20260629.json
ops/envelopes/KOL-SERVER-KFRM-PROBE-20260629.json
```

Для проверки другого recovery envelope можно передать путь первым аргументом:

```bash
scripts/server_kfrm_submission_guard.sh ops/envelopes/example.json
```

## Поведение

При наличии блокеров скрипт печатает список причин, `safe_to_submit=false` и
завершается с кодом 1.

Когда все gates зеленые, скрипт печатает `safe_to_submit=true` и одну будущую
команду submit. Эта строка является инструкцией для оператора, а не действием
скрипта.

## Acceptance

- `script_is_read_only`: да, скрипт использует только локальное чтение файлов и
  read-only HTTP GET к Control Plane.
- `checks_envelope_json`: да, оба envelope проходят JSON validation.
- `checks_existing_probe_idempotency`: да, локальный и live idempotency key
  проверяются для `KOL-SERVER-KFRM-PROBE-20260629`.
- `prints_submit_command_only_if_safe`: да, submit command печатается только
  при пустом списке blockers.
- `does_not_submit`: да, submit-команда не выполняется.

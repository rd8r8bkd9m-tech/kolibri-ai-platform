# Server-kfrm heartbeat recovery envelope

Дата: 2026-06-29  
Роль: `Инженер восстановления heartbeat server-kfrm`  
Scope: создать remote-first recovery envelope, без SSH, рестарта, submit или
изменений кода.

## Артефакт

Envelope:
`ops/envelopes/KOL-SERVER-KFRM-HEARTBEAT-RECOVERY-20260629.json`

Назначение: поручить свежему SRE/control узлу `home` восстановить Agent Host
heartbeat для `server-kfrm` через approved operator channel, затем дождаться и
зафиксировать completed read-only probe
`KOL-SERVER-KFRM-PROBE-20260629`.

Маршрутизация специально не использует stale executor `server-kfrm`:

- `kind`: `generic_implementation`
- `target_node`: `home`
- `allowed_nodes`: `home`
- `excluded_nodes`: `server-kfrm`, `mesh-server-kfrm`, `highload`,
  `primary-candidate`, `qjns`, `uiap`

## Submit command

Команда ниже является инструкцией для оператора. В рамках создания envelope она
не выполнялась.

```bash
KOLIBRI_FACTORY_CONTROL_URL="http://10.99.0.2:9101" \
  ops/kolibri-dispatch --control-url "http://10.99.0.2:9101" \
  submit --file ops/envelopes/KOL-SERVER-KFRM-HEARTBEAT-RECOVERY-20260629.json
```

Перед submit можно проверить JSON:

```bash
python3 -m json.tool ops/envelopes/KOL-SERVER-KFRM-HEARTBEAT-RECOVERY-20260629.json >/dev/null
```

## Stop gates

- Не выполнять задачу на `server-kfrm` или `mesh-server-kfrm`; orchestration
  должен взять только `home`.
- Не продолжать, если нет явного operator approval на live Agent Host recovery.
- Не duplicate-submit `KOL-SERVER-KFRM-PROBE-20260629`, если задача уже
  существует.
- Не считать `mesh-server-kfrm` доказательством executor recovery.
- Не запускать FormulaLM, LLM benchmark, app QA, product QA, browser QA,
  heavy build или Mac compute до fresh heartbeat и completed read-only probe.
- Не делать queue surgery: `cancel`, `retry`, `requeue`, drain/un-drain, прямые
  Redis/spool edits, manual lease edits.
- Не публиковать secrets, auth files, raw private logs или неутвержденные
  node-local paths.

## Rollback / безопасная остановка

Если approval отсутствует, Control Plane не отвечает, probe отсутствует или
heartbeat появился только на `mesh-server-kfrm`, исполнитель должен остановиться
и вернуть blocker artifact. Если Agent Host recovery уже был инициирован через
approved operator channel, rollback заключается в остановке дальнейших workloads
и сохранении `server-kfrm` без FormulaLM/app QA до подтверждения:

- `server-kfrm fresh=true`;
- `health=online`;
- `heartbeat_at` новее preflight snapshot;
- `KOL-SERVER-KFRM-PROBE-20260629` completed именно на `server-kfrm`;
- probe имеет `result_reference` или node-local artifact evidence.

## Acceptance

- Envelope валиден JSON.
- Markdown содержит submit command и rollback/stop gates.
- Код не менялся.
- Recovery acceptance в envelope требует fresh heartbeat `server-kfrm`,
  completed read-only probe и artifact report.

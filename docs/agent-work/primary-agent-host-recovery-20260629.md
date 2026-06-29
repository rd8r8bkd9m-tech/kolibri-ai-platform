# Primary agent-host recovery

Дата: 2026-06-29
Роль: `SRE primary runtime`

## Симптом

После отправки `KOL-PRIMARY-DEVELOPMENT-CONTROL-20260629` узел
`primary-candidate` взял lease и сразу завершил задачу failed:

```text
error_type: runtime_error
error: unsupported task kind: generic_implementation
lease_owner: primary-candidate:agent-host-primary
```

Это соответствует owner-facing сообщению Telegram gateway:

```text
Внутри фабрики упал исполнитель. Я не буду выносить технический мусор в чат:
зафиксировал сбой и переключаю разбор на рабочий контур.
```

## Причина

На `10.99.0.10` был запущен старый `/usr/local/bin/kolibri-agent-host`,
который рекламировал capability `generic_implementation`, но не имел runner
ветки `generic_implementation`.

## Исполнение

На `10.99.0.10` выполнено:

```text
backup /usr/local/bin/kolibri-agent-host -> /usr/local/bin/kolibri-agent-host.bak-<UTC>
scp ops/agent_host.py -> /usr/local/bin/kolibri-agent-host
chmod +x /usr/local/bin/kolibri-agent-host
python3 -m py_compile /usr/local/bin/kolibri-agent-host
systemctl restart kolibri-agent-host.service
```

Проверка после recovery:

```text
sha256: d9d6fbb397f13ece9b0448994fb42cfc98f99b9318bea8e0b06f19f237c94bbd
service: active
pid: 1264822
generic_implementation runner present
```

## Rerun

Создан новый envelope:

```text
ops/envelopes/KOL-PRIMARY-DEVELOPMENT-CONTROL-RERUN-20260629.json
```

Причина нового task id: первая задача уже terminal failed с `max_retries=1`;
ручное изменение terminal state не выполнялось.

## Остаточный риск

Telegram gateway на `main` после остановки duplicate poller больше не
показывает HTTP 409, но журнал всё ещё содержит периодические
`<urlopen error timed out>` при long polling. Connectivity test к
`https://api.telegram.org/` с main проходит, но Python urlopen может занимать
около 10 секунд. Это отдельный сетевой/timeout follow-up, не причина падения
primary generic runner.

# Queue kind compatibility rollout checklist

Дата: 2026-06-29
Роль: `queue_kind_compat_rollout_engineer`
Цель: безопасно довести compatibility-патч
`remote_implementation_runner_ready` до deploy-ready состояния и дать
оператору копируемый rollout/rollback план.

## 1. Проверка патча совместимости

Подтверждено по текущему коду:

- `ops/factory_control.py` сохраняет исходный `kind` в нормализованной задаче и
  в `task["envelope"]["kind"]`; rewrite очереди не выполняется.
- `ops/factory_control.py` добавляет вычисляемый `runner_kind` в compact output
  через `runtime_runner_kind(task)`.
- `remote_implementation_runner_ready` как legacy `required_capability`
  считается совместимым с runner capabilities `implementation` и
  `generic_implementation`.
- `ops/agent_host.py` рекламирует legacy capability в default capabilities.
- `ops/agent_host.py` мапит legacy task kind
  `remote_implementation_runner_ready` в существующий runner path
  `generic_implementation`.
- `tests/test_factory_runtime_queue_contracts.py` проверяет, что stored
  `task["kind"]` остается `remote_implementation_runner_ready`, state остается
  `queued`, а runner classification вычисляется отдельно.

Инвариант rollout: не выполнять cancel/requeue/drain, не редактировать Redis или
spool state, не отправлять новые Control Plane tasks в рамках установки патча.

## 2. Локальная проверка перед rollout

Выполнить из корня репозитория:

```bash
python3 -m json.tool ops/envelopes/KOL-QUEUE-KIND-COMPAT-20260629.json >/dev/null
python3 -m py_compile ops/factory_control.py ops/agent_host.py tests/test_factory_runtime_queue_contracts.py
python3 -m pytest -q tests/test_factory_runtime_queue_contracts.py
bash -n scripts/deploy_readiness_gate.sh scripts/server_kfrm_submission_guard.sh ops/bootstrap_factory_node.sh ops/install_codex_cli.sh
```

Статус в этой worktree:

- `json.tool`: passed.
- `py_compile`: passed.
- `bash -n`: passed for the command above.
- `pytest`: blocked in this Python environment because
  `/opt/homebrew/opt/python@3.14/bin/python3.14` has no `pytest` module.

Если `pytest` отсутствует, установить его в тестовом окружении или выполнить
команду в CI/venv, где он уже доступен. Rollout не начинать, пока pytest-команда
не пройдет с exit code 0.

## 3. Preflight на main node

Задать переменные без секретов:

```bash
export KOL_REPO=/opt/kolibri-ai-platform
export KOL_BACKUP_DIR=/var/backups/kolibri-queue-kind-compat
export KOL_CONTROL_URL=http://127.0.0.1:9101
export KOL_TS="$(date -u +%Y%m%dT%H%M%SZ)"
```

Снять read-only снимок перед изменением:

```bash
date -u
hostname
git -C "$KOL_REPO" status --short
sudo systemctl status kolibri-factory-control --no-pager
sudo systemctl status kolibri-agent-host --no-pager
curl -fsS "$KOL_CONTROL_URL/health"
curl -fsS "$KOL_CONTROL_URL/v1/nodes" > "/tmp/queue-kind-compat.nodes.before.$KOL_TS.json"
curl -fsS "$KOL_CONTROL_URL/v1/tasks?summary=1&compact=1&limit=50" > "/tmp/queue-kind-compat.tasks.before.$KOL_TS.json"
```

Продолжать только если:

- health endpoint отвечает успешно;
- нет неизвестных operator changes, которые будут перезаписаны;
- task snapshot сохранен;
- текущее состояние сервисов понятно оператору.

## 4. Backup и установка

Создать backup текущих runtime-файлов:

```bash
sudo install -d -m 0750 "$KOL_BACKUP_DIR"
sudo install -m 0755 "$KOL_REPO/ops/factory_control.py" "$KOL_BACKUP_DIR/factory_control.py.$KOL_TS"
sudo install -m 0755 "$KOL_REPO/ops/agent_host.py" "$KOL_BACKUP_DIR/agent_host.py.$KOL_TS"
sudo sha256sum "$KOL_BACKUP_DIR/factory_control.py.$KOL_TS" "$KOL_BACKUP_DIR/agent_host.py.$KOL_TS"
```

Установить reviewed checkout на main node стандартным repo deploy путем. Если
main node уже работает из `$KOL_REPO`, достаточно убедиться, что нужная ревизия
на месте:

```bash
git -C "$KOL_REPO" status --short
python3 -m py_compile "$KOL_REPO/ops/factory_control.py" "$KOL_REPO/ops/agent_host.py"
```

## 5. Restart

Перезапустить сначала Control Plane, затем Agent Host, чтобы control-side
compatibility была доступна до следующего lease:

```bash
sudo systemctl restart kolibri-factory-control
sleep 3
sudo systemctl status kolibri-factory-control --no-pager
curl -fsS "$KOL_CONTROL_URL/health"
```

Если Control Plane healthy, перезапустить Agent Host:

```bash
sudo systemctl restart kolibri-agent-host
sleep 5
sudo systemctl status kolibri-agent-host --no-pager
curl -fsS "$KOL_CONTROL_URL/v1/nodes" > "/tmp/queue-kind-compat.nodes.after.$KOL_TS.json"
curl -fsS "$KOL_CONTROL_URL/v1/tasks?summary=1&compact=1&limit=50" > "/tmp/queue-kind-compat.tasks.after.$KOL_TS.json"
```

## 6. Smoke checks

Read-only проверки после restart:

```bash
curl -fsS "$KOL_CONTROL_URL/health"
curl -fsS "$KOL_CONTROL_URL/v1/tasks?summary=1&compact=1&limit=20" | python3 -m json.tool >/tmp/queue-kind-compat.tasks.pretty.$KOL_TS.json
curl -fsS "$KOL_CONTROL_URL/v1/nodes" | python3 -m json.tool >/tmp/queue-kind-compat.nodes.pretty.$KOL_TS.json
journalctl -u kolibri-factory-control -n 100 --no-pager
journalctl -u kolibri-agent-host -n 100 --no-pager
```

Ожидаемые признаки успеха:

- `health` успешен после restart.
- compact task output содержит существующий `kind` и вычисляемый
  `runner_kind`.
- legacy `remote_implementation_runner_ready` не переписывается в queue
  storage.
- Agent Host не пишет `unsupported task kind: remote_implementation_runner_ready`.
- В логах нет повторяющихся traceback, Redis errors или lease-loop failures.

## 7. Rollback

Rollback не должен менять состояние очереди. Восстановить файлы из backup:

```bash
export KOL_REPO=/opt/kolibri-ai-platform
export KOL_BACKUP_DIR=/var/backups/kolibri-queue-kind-compat
export KOL_CONTROL_URL=http://127.0.0.1:9101
export KOL_ROLLBACK_TS="$(basename "$(ls -1t "$KOL_BACKUP_DIR"/factory_control.py.* | head -n 1)" | sed 's/^factory_control.py\.//')"

sudo install -m 0755 "$KOL_BACKUP_DIR/factory_control.py.$KOL_ROLLBACK_TS" "$KOL_REPO/ops/factory_control.py"
sudo install -m 0755 "$KOL_BACKUP_DIR/agent_host.py.$KOL_ROLLBACK_TS" "$KOL_REPO/ops/agent_host.py"
python3 -m py_compile "$KOL_REPO/ops/factory_control.py" "$KOL_REPO/ops/agent_host.py"
sudo systemctl restart kolibri-factory-control
sleep 3
curl -fsS "$KOL_CONTROL_URL/health"
sudo systemctl restart kolibri-agent-host
sleep 5
sudo systemctl status kolibri-factory-control --no-pager
sudo systemctl status kolibri-agent-host --no-pager
journalctl -u kolibri-factory-control -n 100 --no-pager
journalctl -u kolibri-agent-host -n 100 --no-pager
```

После rollback сравнить read-only snapshots:

```bash
curl -fsS "$KOL_CONTROL_URL/v1/nodes" > "/tmp/queue-kind-compat.nodes.rollback.$(date -u +%Y%m%dT%H%M%SZ).json"
curl -fsS "$KOL_CONTROL_URL/v1/tasks?summary=1&compact=1&limit=50" > "/tmp/queue-kind-compat.tasks.rollback.$(date -u +%Y%m%dT%H%M%SZ).json"
```

Не выполнять manual requeue/cancel/drain как часть rollback без отдельного
incident decision.

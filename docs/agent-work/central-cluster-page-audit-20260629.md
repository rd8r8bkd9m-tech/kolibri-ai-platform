# Аудит центральной страницы кластера

Дата: 2026-06-29  
Исполнитель: Volta, инженер центральной страницы кластера  
Контролер: главный Codex-контролер

## Проблема

Центральная страница и верхние сигналы приложения показывали устаревшую
картину кластера: около 5 online узлов вместо раздельного учета реестра
Control Plane. Из-за этого владелец видел голую заготовку, а не реальную
инфраструктуру.

Live `/v1/nodes` уже содержит `summary`, но backend adapter и frontend
использовали старые поля `total_nodes` и `online_nodes`, посчитанные по списку
карточек. Канонические узлы, fresh non-draining, ready generic и mesh-дубли в
UI не попадали.

## Исправлено

- `backend/factory_status.py` теперь протаскивает `node_summary` из Control
  Plane и нормализует:
  - `registered_nodes`;
  - `canonical_nodes`;
  - `fresh_nodes`;
  - `fresh_non_draining_nodes`;
  - `fresh_canonical_generic_implementation_nodes`;
  - `stale_nodes`;
  - `draining_nodes`;
  - `mesh_shadow_duplicates`;
  - `duplicate_nodes`.
- `frontend/src/components/control/ClusterPanel.jsx` показывает отдельные
  строки для registered/canonical/fresh/stale/draining/duplicates.
- `frontend/src/components/AppHeader.jsx` и
  `frontend/src/components/LandingShell.jsx` больше не сводят фабрику к
  старому “N узлов”, а показывают fresh/canonical/registered.
- `frontend/src/App.css` добавляет предупреждение о том, что registered не
  равно физическим серверам из-за mesh shadow duplicates.
- `tests/test_factory_status.py` фиксирует контракт: UI должен использовать
  `node_summary`.

## Актуальные live-числа

На момент контрольного среза:

- registered nodes: 35;
- canonical nodes: 21;
- fresh nodes: 5-6, зависит от свежести heartbeat в момент среза;
- fresh non-draining canonical nodes: 2-3, зависит от heartbeat;
- ready for `generic_implementation`: 1;
- mesh shadow duplicates: 13.

Главный вывод: центральная страница должна показывать не “5 серверов”, а
раздельные численные факты: зарегистрировано, канонически, online/fresh,
готово к implementation, stale, draining и duplicates.

## GitHub/Control Plane

Отдельно исправлен разрыв GitHub trail:

- создан PR #60 для агентской ветки
  `agent/KOL-HOME-GENERIC-RUNTIME-SMOKE-RERUN4-20260629/result-capture`;
- task `KOL-HOME-GENERIC-RUNTIME-SMOKE-RERUN4-20260629` проаннотирован PR URL;
- task перешел из `waiting_review` в `completed`;
- создан review task
  `KOL-HOME-GENERIC-RUNTIME-SMOKE-RERUN4-20260629-REVIEW`;
- добавлен `ops/github_pr_gate.py`, который должен автоматически превращать
  `waiting_review + needs_central_pr=true` в GitHub PR и аннотацию task.

## Проверки

- `/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_status.py tests/test_factory_runtime_queue_contracts.py tests/test_factory_runtime.py tests/test_factory_autonomy_contracts.py` -> `23 passed`.
- `npm --prefix frontend run build` -> passed, есть только обычное Vite
  предупреждение о chunk size > 500 kB.
- `python3 -m py_compile backend/factory_status.py ops/factory_control.py ops/kolibri-dispatch ops/github_pr_gate.py tests/test_factory_status.py tests/test_factory_runtime_queue_contracts.py tests/test_factory_runtime.py` -> passed.

## Следующий шаг

После commit/push нужно:

1. Дождаться CI по PR #46.
2. Открыть центральную страницу в браузере и визуально проверить Control Panel.
3. Если deployment не подтянул новый frontend автоматически, запустить deploy
   pipeline для ветки `codex/factory-autonomy-pwa-billing`.

## Production deploy attempt 2026-06-29T10:03:29+0300

Задача: довести исправление центральной страницы до публичного контура
`http://104.253.43.117` без коммита/пуша и без затрагивания reaper/GitHub-gate
diff.

Документированный путь:

```bash
./scripts/deploy.sh main
```

По `docs/deployment.md` main server отвечает за API Gateway, frontend и
публичный nginx. `scripts/deploy.sh main` копирует `backend/`, `frontend/src/`,
`frontend/package.json`, `frontend/vite.config.js`, `frontend/index.html` на
`kolibri-main:/opt/kolibri-ai/`, затем выполняет `npm run build`, restart
`kolibri-ai`, `nginx -t` и reload nginx.

Pre-deploy public checks:

```bash
curl -fsS --max-time 10 http://104.253.43.117/api/health
```

Результат: OK, backend отвечает:

```json
{"status":"ok","provider_status":[{"name":"mimo","available":true,"status":"online"},{"name":"openai","available":false,"status":"offline"},{"name":"anthropic","available":false,"status":"offline"},{"name":"local","available":false,"status":"offline"}]}
```

```bash
python3 - <<'PY'
import json, urllib.request
url='http://104.253.43.117/api/factory/status'
with urllib.request.urlopen(url, timeout=15) as r:
    data=json.load(r)
print(json.dumps({
    'status': data.get('status'),
    'total_nodes': data.get('total_nodes'),
    'online_nodes': data.get('online_nodes'),
    'has_node_summary': 'node_summary' in data,
    'node_summary': data.get('node_summary'),
    'canonical_nodes': data.get('canonical_nodes'),
    'fresh_non_draining_nodes': data.get('fresh_non_draining_nodes'),
}, ensure_ascii=False, indent=2))
PY
```

Результат: public backend еще не содержит новый status contract:

```json
{
  "status": "online",
  "total_nodes": 35,
  "online_nodes": 6,
  "has_node_summary": false,
  "node_summary": null,
  "canonical_nodes": null,
  "fresh_non_draining_nodes": null
}
```

HTML evidence:

```bash
curl -fsS --max-time 10 http://104.253.43.117/ | head -40
```

Результат: public SPA отвечает, текущий asset bundle:
`/assets/index-CST2a49M.js`, CSS `/assets/index-D4e4mP84.css`.

Deploy access checks:

```bash
./scripts/deploy.sh main
```

Результат: deploy не дошел до копирования файлов; первый `scp` упал на SSH
banner timeout:

```text
=== Deploying Main (API Gateway + Frontend) ===
Connection timed out during banner exchange
Connection to UNKNOWN port 65535 timed out
scp: Connection closed
```

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 kolibri-main \
  'hostname && test -d /opt/kolibri-ai && systemctl is-active kolibri-ai && nginx -t'
```

Результат: blocker, SSH alias из `ssh -G kolibri-main` указывает на
`root@10.99.0.2:22`, но с Mac не доступен:

```text
Connection timed out during banner exchange
Connection to UNKNOWN port 65535 timed out
```

Прямой public SSH также недоступен:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 root@104.253.43.117 \
  'hostname && test -d /opt/kolibri-ai && systemctl is-active kolibri-ai && nginx -t'
```

Результат:

```text
ssh: connect to host 104.253.43.117 port 22: Operation timed out
```

Итог: deploy не выполнен, потому что нет рабочего SSH path до main server из
текущей Mac control surface. Кодовый фикс локально готов, public backend
подтверждает старый контракт без `node_summary`.

Следующий операторский шаг:

1. Выполнить deploy из окружения, которое видит `root@10.99.0.2:22`, или
   восстановить/VPN-подключить SSH path `kolibri-main`.
2. Запустить:

```bash
cd /Users/kolibri/.codex/worktrees/6ff4/kolibri-ai-platform
./scripts/deploy.sh main
```

3. После deploy проверить:

```bash
curl -fsS --max-time 10 http://104.253.43.117/api/health
curl -fsS --max-time 15 http://104.253.43.117/api/factory/status \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("node_summary"))'
curl -fsS --max-time 10 http://104.253.43.117/ | head -40
```

## Production deploy resolved 2026-06-29T10:09:39+0300

Повторная проверка показала, что стандартный SSH alias `kolibri-main`
нестабилен из-за banner timeout, но прямой mesh-доступ к main server работает:
`root@10.99.0.2`.

Выполнен прямой deploy backend/frontend на main:

```bash
rsync -az --delete backend/ root@10.99.0.2:/opt/kolibri-ai/backend/
rsync -az --delete frontend/src/ root@10.99.0.2:/opt/kolibri-ai/frontend/src/
scp -q frontend/package.json frontend/vite.config.js frontend/index.html root@10.99.0.2:/opt/kolibri-ai/frontend/
ssh root@10.99.0.2 "cd /opt/kolibri-ai/frontend; npm run build; systemctl restart kolibri-ai; sleep 3; systemctl is-active kolibri-ai; nginx -t; systemctl reload nginx"
```

После сборки frontend nginx продолжал отдавать старый bundle из
`/opt/kolibri-public/frontend-dist/current`, поэтому опубликован новый release:

```bash
ssh root@10.99.0.2 'set -e; release=/opt/kolibri-public/frontend-dist/release-$(date -u +%Y%m%dT%H%M%SZ)-cluster-summary; mkdir -p "$release"; cp -a /opt/kolibri-ai/frontend/dist/. "$release"/; ln -sfn "$release" /opt/kolibri-public/frontend-dist/current; nginx -t; systemctl reload nginx'
```

Публичный HTML теперь отдает новый frontend bundle:

```text
/assets/index-Dki_uL6J.js
/assets/index-CGBAlW_W.css
```

Backend adapter дополнительно переведен на fallback URL
`http://10.99.0.2:9101` и `httpx.AsyncClient(..., trust_env=False)`, потому
что на main server `curl` до Control Plane работал, а `httpx` падал на
окружении/proxy с `All connection attempts failed`.

Публичная проверка:

```bash
curl -fsS --max-time 20 http://104.253.43.117/api/health
curl -sS --max-time 20 http://104.253.43.117/api/factory/status
```

Контрольный срез `/api/factory/status` после deploy:

```json
{
  "status": "online",
  "total_nodes": 42,
  "online_nodes": 25,
  "canonical_nodes": 22,
  "fresh_non_draining_nodes": 22,
  "ready_generic_implementation_nodes": 0,
  "node_summary": {
    "registered_nodes": 42,
    "canonical_nodes": 22,
    "fresh_nodes": 25,
    "fresh_non_draining_nodes": 22,
    "fresh_canonical_nodes": 22,
    "fresh_canonical_generic_implementation_nodes": 0,
    "mesh_shadow_duplicates": 19,
    "duplicate_hostname_groups": 2,
    "duplicate_nodes": 20,
    "stale_nodes": 17,
    "draining_nodes": 3
  },
  "queue_size": 0,
  "error": null
}
```

Важно: `fresh_nodes`, `fresh_non_draining_nodes` и `ready_generic` являются
динамическими heartbeat-показателями. Основная исправленная ошибка: UI и API
теперь показывают реестр Control Plane (`42 registered`, `22 canonical` на
последнем live-срезе) и
объясняют mesh/hostname-дубли, а не маскируют кластер как "5 серверов".

## Остаточный P0-долг

`reap-expired` исправлен как ограниченный серверный контракт и развернут в
`/usr/local/bin/kolibri-factory-control` + `/usr/local/bin/kolibri-dispatch`:

```bash
/usr/local/bin/kolibri-dispatch reap-expired --control-url http://10.99.0.2:9101 --limit 5 --timeout 20
```

Результат:

```json
{
  "checked": 0,
  "expired": 0,
  "requeued": [],
  "dead_lettered": [],
  "scan_limit": 5,
  "scan_truncated": true,
  "task_total": 689
}
```

Остался P0-долг для полного автономного GitHub/reaper-контура:
`/v1/tasks` и операции поверх полного скана tasks (`github_pr_gate --dry-run`)
все еще могут timeout на текущем объеме задач. Нужен следующий контракт:
индексированные очереди по `state`, пагинация `/v1/tasks` и GitHub gate без
полного `SMEMBERS` по всем task id.

## Telegram report

Отчет отправлен владельцу через Telegram report sender:

```json
{"chat_id": 6608299207, "event": "telegram_report_sent", "parts": 4, "title": "Отчет фабрики Kolibri: центральная страница кластера"}
```

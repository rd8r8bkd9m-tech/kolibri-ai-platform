# Fleet Project Context Rollout

Status: rollout применен ко всем reachable узлам из текущей SSH-топологии.
Остаточный blocker: `hostvds-agent-10` не отвечает по SSH с command node.

Дата: 2026-07-02.

## Цель

Раскатать KFM-схему на узлы Kolibri так, чтобы каждый сервер:

- знал проект через локальный git checkout;
- имел публичную node-local `MEMORY.md` без секретов и приватную
  `/etc/kolibri/agent-memory.md` с правами `0600`;
- имел fetch-only sync timer;
- публиковал для Agent Host переменные `KOLIBRI_OWNER_PROJECT_PATH` и
  `KOLIBRI_RUNTIME_REPO`;
- включал `kolibri-mimo-code.service` только при установленном `mimo` CLI
  или после явного npm-bootstrap флага;
- не открывал публичный unauthenticated listener: MiMo Code допускается только
  на loopback.

## Артефакт

Скрипт: `ops/kolibri-fleet-project-bootstrap.sh`.

Основной dry-run:

```bash
ops/kolibri-fleet-project-bootstrap.sh --dry-run
```

Canary на одном узле после проверки владельцем:

```bash
sudo ops/kolibri-fleet-project-bootstrap.sh
```

Если `mimo` отсутствует, bootstrap не ставит и не включает MiMo Code service.
Установка через npm разрешена только явным действием:

```bash
sudo ops/kolibri-fleet-project-bootstrap.sh \
  --install-mimo-via-npm \
  --mimo-npm-package '<registry-package-name>'
```

Пакет должен быть registry package, не URL/file/git spec. Скрипт не принимает
repo URL с inline credentials.

## Что делает скрипт

- Проверяет, что project/runtime paths абсолютные.
- Если project path уже существует, требует валидный git checkout/worktree и
  не перезаписывает каталог.
- Если repo уже есть, не делает `reset`, `clean`, `pull` или `checkout`.
- Если repo отсутствует, клонирует его через git с credential helper/SSH,
  без печати секретов.
- Создает локальную KFM-память в
  `/var/lib/kolibri-agent/kfm-memory` с правами `0700`.
- Создает `/srv/kolibri-ai-platform/MEMORY.md` как non-secret память проекта
  и исключает ее через `.git/info/exclude`.
- Создает private memory `/etc/kolibri/agent-memory.md` с правами `0600`.
- Обновляет только non-secret env keys в `/etc/kolibri-project-context.env` и
  `/etc/kolibri-agent-host.env`.
- Ставит drop-in для Agent Host:
  `/etc/systemd/system/kolibri-agent-host.service.d/20-project-context.conf`.
- Ставит `kolibri-project-sync.service` и `kolibri-project-sync.timer`.
- Timer делает только `git fetch --prune --tags`, не меняя рабочее дерево.
- MiMo Code service запускает фактический fleet-совместимый режим
  `mimo serve --hostname 127.0.0.1 --port 39231`; bind всегда loopback.
  Secret env для локальной авторизации хранится в `/etc/kolibri/mimocode.env`
  с правами `0600` и не выводится в логи.

## Что скрипт намеренно не делает

- Не запускает fleet rollout сам по себе.
- Не печатает и не переносит секреты.
- Не меняет firewall/nginx/VPN.
- Не включает публичный listener.
- Не чистит dirty runtime repos.
- Не рестартует Agent Host без явного `--restart-agent-host`.
- Не затирает чужие unmanaged systemd unit/drop-in файлы без
  `--force-managed-overwrite`.

## Рекомендуемый rollout

1. На выбранном canary-узле выполнить `--dry-run`.
2. Проверить, что project path, runtime repo и memory root соответствуют
   ожидаемому серверному layout.
3. Выполнить bootstrap без `--restart-agent-host`.
4. Проверить:
   - `systemctl is-enabled kolibri-project-sync.timer`;
   - `systemctl list-timers kolibri-project-sync.timer`;
   - `/etc/kolibri-agent-host.env` содержит `KOLIBRI_OWNER_PROJECT_PATH` и
     `KOLIBRI_RUNTIME_REPO`;
   - `/var/lib/kolibri-agent/kfm-memory` не содержит секретов;
   - `kolibri-mimo-code.service` либо loopback-only и active, либо осознанно
     skipped из-за отсутствующего/неподдержанного `mimo`.
5. Только после canary evidence решить, нужен ли
   `--restart-agent-host` на этом узле.
6. Расширять rollout малыми партиями. Узлы с dirty runtime repo не чистить;
   фиксировать blocker и продолжать fetch-only режим.

## Acceptance

- `bash -n ops/kolibri-fleet-project-bootstrap.sh` проходит.
- Dry-run не пишет файлы и не запускает сервисы.
- Повторный запуск идемпотентен.
- Agent Host получает project context через env/drop-in.
- Sync timer включен и не меняет checkout.
- MiMo Code не стартует на `0.0.0.0` или внешнем IP.
- Legacy services вроде `mimo-acp.service`/`mimo-agent.service`, если они
  поднимают `mimo serve` на `0.0.0.0`, должны быть отключены или переведены на
  loopback до acceptance.
- Bootstrap не требует и не выводит токены, cookies, private keys, provider
  credentials или OAuth-сессии.

## Blockers

- `project_path_exists_without_git`: каталог существует, но не является git repo.
- `repo_url_with_inline_credentials_forbidden`: URL содержит credentials.
- `unmanaged_systemd_target`: target unit/drop-in уже существует и не помечен
  как managed by bootstrap.
- `mimo_cli_missing`: `mimo` отсутствует, а npm-bootstrap не разрешен.
- `systemctl_unavailable`: systemd timer нельзя установить на этом узле.

## Rollback

Для canary rollback без удаления данных:

```bash
sudo systemctl disable --now kolibri-project-sync.timer
sudo systemctl disable --now kolibri-mimo-code.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/kolibri-project-sync.service
sudo rm -f /etc/systemd/system/kolibri-project-sync.timer
sudo rm -f /etc/systemd/system/kolibri-mimo-code.service
sudo rm -f /etc/systemd/system/kolibri-agent-host.service.d/20-project-context.conf
sudo systemctl daemon-reload
```

KFM memory и runtime repo не удалять автоматически: сначала проверить, что в них
нет полезных локальных артефактов.

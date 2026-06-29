# Telegram long-polling worker audit

Дата проверки: 2026-06-29. Роль: SRE Telegram long-polling.

## Follow-up выполнен главным исполнителем

После audit дублирующий poller на `10.99.0.10` был остановлен и отключен:

```bash
systemctl stop kolibri-telegram-gateway.service
systemctl disable kolibri-telegram-gateway.service
```

Проверка:

- `10.99.0.10`: `kolibri-telegram-gateway.service` стал `inactive` и
  `disabled`;
- `10.99.0.2`: основной `kolibri-telegram-gateway.service` остался `active`;
- в свежем журнале `10.99.0.2` после остановки дубля не было новых
  `TELEGRAM_GETUPDATES_CONFLICT` / HTTP `409`, остался только сетевой timeout.

## Вывод

Найден второй active long-polling worker с тем же Telegram bot token, который конфликтует с боевым `kolibri-telegram-gateway` на control node.

Conflict worker:

- Host: `10.99.0.10`, hostname `kolibri`, node `primary-candidate`.
- Unit: `kolibri-telegram-gateway.service`.
- Status: `enabled`, `active (running)`.
- Current PID: `1237283`.
- Command: `/usr/bin/python3 /usr/local/bin/kolibri-telegram-gateway --control-url http://10.99.0.10:9101`.
- Code path: `/usr/local/bin/kolibri-telegram-gateway:254` calls Telegram `getUpdates`; `run_once()` calls `self.telegram.get_updates(...)`.

Production/control gateway that should keep ownership:

- Host: `10.99.0.2`, hostname `kolibri-main-api`.
- Unit: `kolibri-telegram-gateway.service`.
- Status: `active (running)`, unit file currently `disabled` but process is live.
- Current PID: `2186292`.
- Command: `python3 /usr/local/bin/kolibri-telegram-gateway`.
- Code path: `/usr/local/bin/kolibri-telegram-gateway:636` calls Telegram `getUpdates`.

No production process was stopped or disabled during this audit.

## Evidence

### Same bot token

I compared token fingerprints only, without printing token values:

```text
MATCH main and primary telegram.env token fingerprints
```

This proves `10.99.0.2:/etc/kolibri/telegram.env` and
`10.99.0.10:/etc/kolibri/telegram.env` are configured for the same bot.

### Runtime process evidence

On `10.99.0.2`:

```text
2186292  1  kolibri  Mon Jun 29 08:43:51 2026  python3 /usr/local/bin/kolibri-telegram-gateway
```

On `10.99.0.10`:

```text
1237283  1  root     Mon Jun 29 11:21:04 2026  /usr/bin/python3 /usr/local/bin/kolibri-telegram-gateway --control-url http://10.99.0.10:9101
```

`systemctl cat` on `10.99.0.10` shows:

```ini
EnvironmentFile=/etc/kolibri/telegram.env
ExecStart=/usr/bin/python3 /usr/local/bin/kolibri-telegram-gateway --control-url http://10.99.0.10:9101
```

### Conflict logs

On `10.99.0.2`:

```text
conflict_count=249
first=Jun 29 10:20:36
last=Jun 29 11:18:49
```

Recent main logs then changed to Telegram urlopen timeouts, but the process is still active.

On `10.99.0.10`:

```text
conflict_count=250
first=Jun 29 10:20:41
last=Jun 29 11:41:47
```

Recent primary logs explicitly say:

```text
{"event": "telegram_polling_conflict", "error_type": "TELEGRAM_GETUPDATES_CONFLICT", "recovery": "stop the other Telegram long-polling worker or move this gateway to webhook/send-only mode"}
```

Primary journal also shows earlier gateway PIDs before the current one:
`1222031`, `1227635`, `1228619`, then current `1237283`.

### Code callers of getUpdates

Repository:

- `ops/telegram_gateway.py:636` calls `self.call("getUpdates", ...)`.

Production binaries:

- `10.99.0.2:/usr/local/bin/kolibri-telegram-gateway:636` calls `getUpdates`.
- `10.99.0.10:/usr/local/bin/kolibri-telegram-gateway:254` calls `getUpdates`.

Legacy/non-running code also exists on `10.99.0.10`:

- `/opt/kolibri/repo/scripts/telegram_task_gateway.py` has `getUpdates` and `run_polling`, but I found no active process or systemd unit running it.

## Negative checks

Checked and did not find another active Kolibri Telegram poller on:

- `10.99.0.6` / `kolibri-worker-backup`: no Telegram gateway/polling process or service.
- `10.99.0.4` / `kolibri-tools-executor`: no Telegram gateway/polling process or service.
- `10.99.0.5` / `kolibri-inference-recovery`: no Telegram gateway/polling process or service. One `mimo` task mentions Telegram in the owner prompt, but it is not a Telegram API poller.

Unreachable during this pass:

- `10.99.0.3`: SSH banner timed out.
- `kolibri-home` / `178.207.11.90:2222`: SSH timed out.
- `server-kfrm`: SSH timed out.

Container check:

- `10.99.0.2`: Docker not installed.
- `10.99.0.10` and `10.99.0.6`: no running Docker containers matching Telegram/bot/poll/gateway.
- `10.99.0.4`: `docker ps` hung and was interrupted; host `ps`/systemd were already negative.

Non-conflicting Telegram services on main:

- `kolibri-telegram-mesh-outbound-relay.service`, PID `1439866`, is send-only. Its code calls Telegram `sendMessage`, reads mesh messages, and does not call `getUpdates`.
- `kolibri-factory-lease-watchdog.service` can send Telegram notifications on action but does not call `getUpdates`.

Local Mac note:

- Local PID `3099` runs `/Users/kolibri/construction-estimate-agent/core/tg_bot.js` and uses Telegram long polling, but its token fingerprint differs from production. It is not the conflict source for `kolibri-telegram-gateway`.

## Safe stop/disable plan

Target only the duplicate poller on `10.99.0.10`. Leave `10.99.0.2` running.

Preflight:

```bash
ssh root@10.99.0.10 'systemctl status kolibri-telegram-gateway --no-pager; ps -p 1237283 -o pid,ppid,user,lstart,etime,cmd'
ssh root@10.99.0.2 'systemctl status kolibri-telegram-gateway --no-pager'
```

Stop duplicate worker:

```bash
ssh root@10.99.0.10 'systemctl stop kolibri-telegram-gateway.service'
```

Disable duplicate autostart:

```bash
ssh root@10.99.0.10 'systemctl disable kolibri-telegram-gateway.service'
```

Verification after 60-90 seconds:

```bash
ssh root@10.99.0.10 'systemctl is-active kolibri-telegram-gateway.service || true; ps -eo pid,cmd | grep -F /usr/local/bin/kolibri-telegram-gateway | grep -v grep || true'
ssh root@10.99.0.2 'journalctl -u kolibri-telegram-gateway --since "2 minutes ago" --no-pager | grep -E "409|TELEGRAM_GETUPDATES_CONFLICT|telegram_polling_conflict" || true'
ssh root@10.99.0.2 'systemctl status kolibri-telegram-gateway --no-pager'
```

Rollback:

```bash
ssh root@10.99.0.10 'systemctl enable --now kolibri-telegram-gateway.service'
```

If the service is restarted by another automation after disable, then use a stronger operator-approved guard:

```bash
ssh root@10.99.0.10 'systemctl mask kolibri-telegram-gateway.service'
```

Do not mask by default unless it resurrects; masking is harder to forget during future failover.

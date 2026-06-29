# GoMesh MikroTik home access report

Дата: 2026-06-29 15:27 MSK / 12:27 UTC.
Контур: primary `10.99.0.10`, main `10.99.0.2`, home `10.99.0.1`, MikroTik `192.168.88.1`.

## Итог

Попытка зайти к home через MikroTik/GoMesh не прошла: home mesh-agent и
MikroTik management из mesh-контуров сейчас недоступны по сети. Staged
RouterOS profile валиден, но live путь к RouterOS не открыт, поэтому
автоматически включить монитор/Mimo на home сейчас нельзя.

## Проверки

### Home mesh-agent

Команды:

```bash
ssh ladik@10.99.0.1 'curl -fsS --max-time 8 http://10.99.0.1:8081/health'
curl -fsS --max-time 8 http://10.99.0.1:8081/health
```

Результат:

- `ssh ladik@10.99.0.1:22`: timeout.
- `http://10.99.0.1:8081/health`: timeout с Mac, `main` и `primary`.
- Collector на primary:
  `/opt/kolibri/repo/.run/gomesh-home-live-20260629T122213Z/summary.json`.
- Collector result: `ok=false`, `required_failures=["home mesh-agent health check failed"]`.

### MikroTik live access

Команда:

```bash
cd /opt/kolibri/repo
python3 scripts/kolibri_gomesh_routeros_live_audit.py --pretty
```

Результат:

- Router host: `192.168.88.1`.
- TCP checks timed out: `22`, `80`, `443`, `8291`, `8728`, `8729`.
- `manual_live_dump_required=true`.
- Без read-only API user audit был невозможен из-за отсутствующего password source.

После подготовки read-only API bundle:

```bash
python3 scripts/kolibri_gomesh_routeros_api_bootstrap.py --pretty
/usr/local/sbin/kolibri-gomesh-routeros-api-bundle-verify --pretty
python3 scripts/kolibri_gomesh_routeros_live_audit.py \
  --api-user kolibri-ro \
  --api-password-file /etc/kolibri-gomesh/routeros-api.password \
  --pretty
```

Результат:

- Bundle verify: `ok=true`.
- Password file and command files mode: `0600`.
- Password was not printed.
- Create command policy: `read,api`.
- No routing/firewall changes in API bootstrap files.
- Live API probe still timed out on `192.168.88.1:8728`.

### RouterOS profile and service routes

Profile audit:

```bash
python3 scripts/kolibri_gomesh_routeros_profile_audit.py --pretty
```

Результат:

- `ok=true`.
- Expected policy table: `kolibri-home-gw`.
- Expected home next hop: `192.168.88.210`.
- Blockers: none.

Service route audit:

```bash
python3 scripts/kolibri_gomesh_service_route_audit.py --pretty
```

Результат:

- `ok=false`.
- Direct route works for checked targets.
- Mesh route failed for `youtube` and `xiaomi-mimo-platform`.
- Recommended action: `keep_direct_mesh_needs_fix`.

## Prepared artifacts on primary

- `/etc/kolibri-gomesh/routeros-live-dump/winbox-dump-commands.txt`
- `/etc/kolibri-gomesh/routeros-api/create-kolibri-routeros-api-user.rsc`
- `/etc/kolibri-gomesh/routeros-api/remove-kolibri-routeros-api-user.rsc`
- `/etc/kolibri-gomesh/routeros-api.password`

The password file is private and was not printed.

## Manual MikroTik dump commands

These commands are read-only and were written to
`/etc/kolibri-gomesh/routeros-live-dump/winbox-dump-commands.txt` on primary:

```routeros
/system/script/run kolibri-home-gw-status
/routing/table/print detail where name="kolibri-home-gw"
/ip/route/print detail where comment~"Kolibri Home gateway" or routing-table="kolibri-home-gw"
/routing/rule/print detail where comment~"Kolibri Home gateway"
/ip/firewall/nat/print detail where comment~"Kolibri DNS redirect"
/system/script/print detail where name~"kolibri-home-gw"
/system/scheduler/print detail where name~"kolibri-home-gw"
/ip/dns/print
```

## Blocker

Current blocker is network reachability, not missing scripts:

1. `10.99.0.1` is not reachable on SSH or mesh-agent health.
2. `192.168.88.1` is not reachable on SSH, HTTP, WinBox, RouterOS API or API-SSL
   from the GoMesh exits.
3. MikroTik profile artifact is valid, but live state cannot be read until the
   router management path or manual dump is restored.
4. Mimo task `KOL-META-MIMO-ORCHESTRATOR-PRIMARY-20260629` was submitted to
   primary-candidate and failed with `runner_empty_response`.

## Next machine action

Use envelope `ops/envelopes/KOL-GOMESH-HOME-MIKROTIK-RECOVERY-20260629.json`
to continue on primary without touching secrets or changing live RouterOS
configuration unless an authenticated live management path is restored.

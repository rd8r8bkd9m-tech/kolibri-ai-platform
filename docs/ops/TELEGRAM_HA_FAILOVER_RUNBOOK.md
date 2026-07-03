# Telegram HA Failover Runbook

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Telegram Bot API                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
          ┌─────────▼─────────┐  ┌──────▼──────────┐
          │  PRIMARY Gateway  │  │  STANDBY Gateway │
          │  (polling/webhook)│  │  (send-only)     │
          └─────────┬─────────┘  └──────┬──────────┘
                    │                   │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Control Plane     │
                    │  (factory control) │
                    └───────────────────┘
```

## Key Files

| File | Purpose |
|------|---------|
| `ops/telegram_failover_guard.py` | HA guard: dual-receiver detection, state replication, promotion logic |
| `ops/telegram_gateway.py` | Gateway main: polling, Redis HA lease/offset state, task handling, durable owner notification spool |
| `ops/telegram_superfactory.py` | Receiver plan: validates mode conflicts |
| `ops/systemd/kolibri-telegram-gateway.service` | Systemd service for primary gateway |
| `tests/test_telegram_failover_guard.py` | Guard unit tests |

## Durable HA State

Production HA should set `TELEGRAM_HA_REDIS_URL` on every gateway instance. When it is set, `ops/telegram_gateway.py` uses Redis for:

- `kolibri:telegram:ha:polling_lease`: single active `getUpdates` lease, refreshed by the current active gateway.
- `kolibri:telegram:ha:offset`: shared Telegram update offset.
- `kolibri:telegram:ha:notification_spool`: owner text notifications queued before send and removed only after Telegram accepts them.

`TELEGRAM_HA_REDIS_PREFIX` can override the key prefix. `TELEGRAM_GATEWAY_ID` should be stable per instance; otherwise the gateway uses role, hostname, and pid. Startup logs never print the Redis URL, token, owner chat id, or credentials.

If Redis coordination is not configured or cannot be initialized, the gateway falls back to the existing local state file and logs `telegram_ha_redis_coordination_unavailable` with a redacted error. That fallback is safe for a single receiver, but it is not the durable HA mode for multi-node failover.

## Offset Acknowledgment Rule

The gateway must acknowledge a Telegram update only after successful handling. `run_once()` now:

1. Flushes any pending owner notification spool entries.
2. Acquires the Redis polling lease when Redis HA is configured.
3. Calls `getUpdates` with the Redis offset when present, otherwise the local file offset.
4. Handles each update.
5. Commits `update_id + 1` to local state and Redis only after the handler returns.

If the handler raises, the offset is not advanced, so Telegram can redeliver the owner update on the next healthy poller.

## Runtime Verification Commands

### 1. Verify Single Active Receiver

```bash
# Check primary gateway is polling
systemctl status kolibri-telegram-gateway.service | grep -E "Active:|polling"

# Verify standby is send-only
systemctl status kolibri-telegram-state-replica.timer | grep -E "Active:|Last"

# Check no duplicate getUpdates processes
ps aux | grep -E "getUpdates|telegram.*poll" | grep -v grep
```

### 2. Verify Redis Lease, Offset, and Spool State

Use a sanitized Redis shell on the host that already has access to Redis. Do not paste Redis URLs with credentials into logs.

```bash
redis-cli GET kolibri:telegram:ha:polling_lease
redis-cli GET kolibri:telegram:ha:offset
redis-cli LLEN kolibri:telegram:ha:notification_spool
```

Expected:
- exactly one active lease owner while polling is enabled;
- offset is numeric and monotonic;
- spool is usually `0`, but may be nonzero while Telegram send is down and should drain after failover.

### 3. Verify File State Replication Fallback

```bash
# Check state hash matches
python3 -c "
from ops.telegram_failover_guard import verify_state_replication
from pathlib import Path
result = verify_state_replication(
    Path('/var/lib/kolibri-telegram-gateway/state.json'),
    Path('/var/lib/kolibri-telegram-standby/state.json')
)
print(result['message'])
print(f'Match: {result[\"match\"]}')
"
```

### 4. Check Primary Health

```bash
# Verify heartbeat freshness
ls -la /var/lib/kolibri-telegram-gateway/*.heartbeat
cat /var/lib/kolibri-telegram-gateway/*.heartbeat | python3 -m json.tool

# Check gateway logs for health
journalctl -u kolibri-telegram-gateway.service -n 20 --no-pager | grep -E "health|heartbeat|receiver"
```

### 5. Failover Guard Status

```bash
# Run full failover status check
python3 -c "
from ops.telegram_failover_guard import (
    load_failover_state,
    check_primary_health,
    detect_dual_receiver,
    format_failover_status
)
from pathlib import Path

state = load_failover_state(Path('/var/lib/kolibri-telegram-gateway/failover.json'))
health = check_primary_health(health_data={'health': 'online', 'heartbeat_at': str(__import__('time').time())})
print(format_failover_status(state, health))
"
```

## Failover Scenarios

### Scenario 1: Primary Healthy (Normal Operation)

**Expected State:**
- Primary: polling, active receiver
- Standby: send-only, no polling conflict
- Redis polling lease: owned by one gateway only
- Offset: shared in Redis and advanced only after successful update handling

**Commands:**
```bash
# Verify primary is active
systemctl is-active kolibri-telegram-gateway.service

# Verify standby is not polling
systemctl is-active kolibri-telegram-state-replica.timer

# Check no dual receivers
python3 -c "
from ops.telegram_failover_guard import detect_dual_receiver
result = detect_dual_receiver(primary_polling=True, standby_polling=False, webhook_active=False)
assert result['ok'], f'Dual receiver detected: {result[\"violations\"]}'
print('Single receiver verified')
"
```

### Scenario 2: Primary Unhealthy - Promotion Eligible

**Expected State:**
- Primary: offline or stale heartbeat
- Standby: eligible for promotion
- Redis polling lease expired or unavailable to the failed primary
- Redis offset and notification spool available to standby
- Replication verified when using file-state fallback

**Commands:**
```bash
# Check primary health
python3 -c "
from ops.telegram_failover_guard import check_primary_health
health = check_primary_health(health_data={'health': 'offline', 'heartbeat_at': str(__import__('time').time() - 300)})
print(f'Primary healthy: {health[\"ok\"]}')
print(f'Promotion eligible: {not health[\"ok\"]}')
"

# Verify replication before promotion
python3 -c "
from ops.telegram_failover_guard import verify_state_replication
from pathlib import Path
result = verify_state_replication(
    Path('/var/lib/kolibri-telegram-gateway/state.json'),
    Path('/var/lib/kolibri-telegram-standby/state.json')
)
print(f'Replication OK: {result[\"ok\"]}')
"
```

When Redis HA is configured, promotion does not require copying the Telegram offset from the failed primary: the standby reads `kolibri:telegram:ha:offset` and drains `kolibri:telegram:ha:notification_spool` before polling.

### Scenario 3: Dual Receiver Detection

**Expected State:**
- Both gateways polling simultaneously (VIOLATION)

**Commands:**
```bash
# Detect dual receivers
python3 -c "
from ops.telegram_failover_guard import detect_dual_receiver
result = detect_dual_receiver(primary_polling=True, standby_polling=True, webhook_active=False)
if not result['ok']:
    print(f'VIOLATION: {result[\"violations\"][0][\"message\"]}')
else:
    print('No dual receiver detected')
"

# Emergency: stop standby polling
sudo systemctl stop kolibri-telegram-standby-gateway.service
```

### Scenario 4: State Replication Mismatch

**Expected State:**
- Primary and standby state hashes differ (REPLICATION STALE)

**Commands:**
```bash
# Check replication status
python3 -c "
from ops.telegram_failover_guard import verify_state_replication
from pathlib import Path
result = verify_state_replication(
    Path('/var/lib/kolibri-telegram-gateway/state.json'),
    Path('/var/lib/kolibri-telegram-standby/state.json')
)
if not result['ok']:
    print(f'Replication mismatch: primary={result[\"primary_hash\"]}, standby={result[\"standby_hash\"]}')
else:
    print('Replication verified')
"

# Force replication sync
sudo systemctl restart kolibri-telegram-state-replica.timer
```

## Emergency Procedures

### Stop All Receivers

```bash
sudo systemctl stop kolibri-telegram-gateway.service
sudo systemctl stop kolibri-telegram-standby-gateway.service
sudo systemctl stop kolibri-telegram-state-replica.timer
```

### Force Promotion (Manual Override)

```bash
# Only when primary is confirmed down and replication is verified
python3 -c "
from ops.telegram_failover_guard import load_failover_state, save_failover_state
from pathlib import Path
state = load_failover_state(Path('/var/lib/kolibri-telegram-gateway/failover.json'))
state.promotion_blocked = False
save_failover_state(state, Path('/var/lib/kolibri-telegram-gateway/failover.json'))
"

sudo systemctl start kolibri-telegram-standby-gateway.service
```

### Block Promotion

```bash
python3 -c "
from ops.telegram_failover_guard import load_failover_state, save_failover_state
from pathlib import Path
state = load_failover_state(Path('/var/lib/kolibri-telegram-gateway/failover.json'))
state.promotion_blocked = True
save_failover_state(state, Path('/var/lib/kolibri-telegram-gateway/failover.json'))
"
```

## Security Constraints

1. **No secrets in logs**: Never print bot tokens, chat IDs, owner IDs
2. **Single receiver**: Only one gateway processes getUpdates at a time
3. **No live promotion**: Standby does not promote while primary is healthy
4. **State verification**: Redis HA state must be reachable, or file replication hash must match before file-state fallback promotion
5. **Cooldown**: 300s minimum between promotion attempts
6. **Delayed offset ack**: Do not advance offset until the update handler succeeds
7. **Durable owner notifications**: Queue owner text notifications before send and remove them only after successful Telegram delivery

## Monitoring Checklist

- [ ] Primary gateway active and polling
- [ ] Standby gateway in send-only mode
- [ ] Redis polling lease has exactly one owner
- [ ] Redis offset is monotonic
- [ ] Notification spool drains after failover
- [ ] State replication hash matched when file fallback is used
- [ ] Heartbeat freshness < 120s
- [ ] No dual receiver violations
- [ ] Promotion not blocked (unless intentional)

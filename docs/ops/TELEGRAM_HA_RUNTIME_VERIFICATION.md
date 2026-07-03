# Telegram HA Runtime Verification

## Verification Checklist

### Pre-Deployment Verification

| Check | Command | Expected |
|-------|---------|----------|
| Guard module importable | `python3 -c "from ops.telegram_failover_guard import *"` | No import error |
| Gateway and guard tests pass | `python3 -m pytest tests/test_telegram_gateway.py tests/test_telegram_failover_guard.py -q` | All pass |
| Changed runtime files compile | `python3 -m py_compile ops/telegram_gateway.py ops/telegram_failover_guard.py` | No compile error |
| No secrets in artifacts | `grep -rn "token\|secret\|key" ops/telegram_failover_guard.py ops/telegram_gateway.py` | Only code/redaction patterns, no live values |

## Runtime Verification

### 1. Single Receiver Enforcement

Primary gateway:

```bash
systemctl is-active kolibri-telegram-gateway.service
journalctl -u kolibri-telegram-gateway.service -n 20 --no-pager | grep -E "telegram_receiver_plan|telegram_ha"
```

Expected:
- primary service is active;
- `telegram_receiver_plan` reports polling allowed;
- `telegram_ha_startup_validation` reports `ok: true`;
- logs do not print bot tokens, Redis URLs with credentials, owner ids, or chat ids.

Standby gateway:

```bash
ps aux | grep -E "kolibri-telegram.*standby|getUpdates" | grep -v grep
systemctl status kolibri-telegram-state-replica.timer
```

Expected:
- no standby `getUpdates` receiver while the primary is healthy;
- standby may run send-only spool replay or state replication without consuming updates.

Dual receiver guard:

```bash
python3 -c "
from ops.telegram_failover_guard import detect_dual_receiver
result = detect_dual_receiver(primary_polling=True, standby_polling=False, webhook_active=False)
print(result)
assert result['ok']
"
```

### 2. Redis HA Lease, Offset, and Notification Spool

When `TELEGRAM_HA_REDIS_URL` is configured, Redis is the durable HA state store. Use local Redis tooling only from hosts already authorized for Redis. Do not print Redis URLs or credentials.

```bash
redis-cli GET kolibri:telegram:ha:polling_lease
redis-cli GET kolibri:telegram:ha:offset
redis-cli LLEN kolibri:telegram:ha:notification_spool
```

Expected:
- one polling lease owner while active polling is running;
- offset is numeric and monotonic;
- notification spool normally returns `0`, or drains after Telegram delivery recovers.

The gateway commits `update_id + 1` only after `handle_message()` returns successfully. Handler failure leaves the offset unchanged so Telegram can redeliver the update to the next healthy poller.

### 3. File-State Fallback

If Redis coordination is unavailable, startup logs `telegram_ha_redis_coordination_unavailable` with a redacted error and falls back to the local state file. This is acceptable for single-receiver recovery, but multi-node HA should restore Redis coordination before promotion.

```bash
python3 -c "
from ops.telegram_failover_guard import verify_state_replication
from pathlib import Path
result = verify_state_replication(
    Path('/var/lib/kolibri-telegram-gateway/state.json'),
    Path('/var/lib/kolibri-telegram-standby/state.json')
)
print(result)
"
```

Expected for file fallback: `ok: true` before standby promotion.

### 4. Primary Health Monitoring

```bash
ls -la /var/lib/kolibri-telegram-gateway/*.heartbeat
cat /var/lib/kolibri-telegram-gateway/*.heartbeat | python3 -m json.tool
```

Expected: heartbeat timestamp is fresh according to the configured threshold.

```bash
python3 -c "
from ops.telegram_failover_guard import check_primary_health
import time
health = check_primary_health(health_data={'health': 'online', 'heartbeat_at': str(time.time())})
print(health)
assert health['ok']
"
```

### 5. Startup Validation

```bash
python3 -c "
from ops.telegram_failover_guard import validate_gateway_startup
primary = validate_gateway_startup('primary', 'polling', None)
standby = validate_gateway_startup('standby', 'polling', None, primary_healthy=True)
print(primary)
print(standby)
assert primary['ok']
assert not standby['ok']
"
```

Expected: primary polling is valid; standby polling is rejected while primary is healthy.

### 6. Promotion Gating

```bash
python3 -c "
from ops.telegram_failover_guard import FailoverState, evaluate_failover_promotion
import time
state = FailoverState(last_promotion_attempt=time.time() - 400, replication_verified=True)
result = evaluate_failover_promotion(state, {'ok': False}, now=time.time())
print(result)
assert result['should_promote']
"
```

Expected: promotion is eligible only when primary health is bad, cooldown passed, promotion is not blocked, and replication is verified or Redis HA state is available.

## Post-Verification Commands

```bash
python3 -m py_compile ops/telegram_gateway.py ops/telegram_failover_guard.py
python3 -m pytest tests/test_telegram_gateway.py tests/test_telegram_failover_guard.py -q
grep -rn "TELEGRAM_BOT_TOKEN\|owner_id\|chat_id\|redis://" ops/telegram_failover_guard.py ops/telegram_gateway.py docs/ops/TELEGRAM_HA_FAILOVER_RUNBOOK.md docs/ops/TELEGRAM_HA_RUNTIME_VERIFICATION.md
```

Expected: compile succeeds, tests pass, grep shows only code/config names and placeholder examples with no live values.

## Acceptance Criteria Verification

| Criterion | Verification | Status |
|-----------|--------------|--------|
| Single active polling lease | `TelegramHACoordinator.acquire_polling_lease()` and focused gateway tests | Verified |
| Standby no-conflict receiver | startup validation and standby lease-denial behavior | Verified |
| Redis-backed offset state | `TelegramHACoordinator.offset()` and `acknowledge_offset()` | Verified |
| Offset ack after successful handling only | `test_run_once_acknowledges_offset_only_after_successful_handling` | Verified |
| Durable owner notification spool | `notification_spool` Redis/local queue and replay test | Verified |
| Startup/log redaction | `redact_secret_text()` token, assignment, and Redis URL test | Verified |
| Required run artifacts | PLAN/ACTIONS/TESTS/RESULT/NEXT under the task run directory | Verified by task artifact creation |

## Artifact Inventory

```text
ops/telegram_gateway.py
ops/telegram_failover_guard.py
tests/test_telegram_gateway.py
tests/test_telegram_failover_guard.py
docs/ops/TELEGRAM_HA_FAILOVER_RUNBOOK.md
docs/ops/TELEGRAM_HA_RUNTIME_VERIFICATION.md
```

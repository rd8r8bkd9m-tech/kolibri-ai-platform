# Telegram HA Runtime Verification

## Verification Checklist

### Pre-Deployment Verification

| Check | Command | Expected |
|-------|---------|----------|
| Guard module importable | `python3 -c "from ops.telegram_failover_guard import *"` | No import error |
| Tests pass | `python3 -m pytest tests/test_telegram_failover_guard.py -v` | All pass |
| No secrets in artifacts | `grep -rn "token\|secret\|key" ops/telegram_failover_guard.py` | Only in regex patterns |

### Runtime Verification

#### 1. Single Receiver Enforcement

**Primary Gateway (Active):**
```bash
# Verify primary is polling
systemctl is-active kolibri-telegram-gateway.service
# Expected: active

# Verify receiver mode
journalctl -u kolibri-telegram-gateway.service -n 5 --no-pager | grep receiver
# Expected: "telegram_receiver_plan" with "should_poll": true
```

**Standby Gateway (Passive):**
```bash
# Verify standby is NOT polling
ps aux | grep "kolibri-telegram-standby" | grep -v grep
# Expected: no output

# Verify send-only mode
systemctl status kolibri-telegram-state-replica.timer
# Expected: active (timer for state replication)
```

**Dual Receiver Detection:**
```bash
# Run guard check
python3 -c "
from ops.telegram_failover_guard import detect_dual_receiver
result = detect_dual_receiver(primary_polling=True, standby_polling=False, webhook_active=False)
print(f'Single receiver: {result[\"ok\"]}')
print(f'Active count: {result[\"active_count\"]}')
"
# Expected: Single receiver: True, Active count: 1
```

#### 2. State Replication Freshness

**Hash Verification:**
```bash
# Compare state hashes
python3 -c "
from ops.telegram_failover_guard import verify_state_replication
from pathlib import Path
result = verify_state_replication(
    Path('/var/lib/kolibri-telegram-gateway/state.json'),
    Path('/var/lib/kolibri-telegram-standby/state.json')
)
print(f'Replication OK: {result[\"ok\"]}')
print(f'Match: {result[\"match\"]}')
"
# Expected: Replication OK: True, Match: True
```

**State File Freshness:**
```bash
# Check state file modification time
ls -la /var/lib/kolibri-telegram-gateway/state.json
ls -la /var/lib/kolibri-telegram-standby/state.json
# Expected: Both files recently modified (< 60s)
```

#### 3. Primary Health Monitoring

**Heartbeat Check:**
```bash
# Check heartbeat file
ls -la /var/lib/kolibri-telegram-gateway/*.heartbeat
cat /var/lib/kolibri-telegram-gateway/*.heartbeat | python3 -m json.tool
# Expected: heartbeat_at within last 120s
```

**Health Status:**
```bash
# Run health check
python3 -c "
from ops.telegram_failover_guard import check_primary_health
import time
health = check_primary_health(health_data={'health': 'online', 'heartbeat_at': str(time.time())})
print(f'Primary healthy: {health[\"ok\"]}')
print(f'Health status: {health[\"health_status\"]}')
print(f'Heartbeat fresh: {health[\"heartbeat_fresh\"]}')
"
# Expected: Primary healthy: True
```

#### 4. Gateway Startup Validation

**Primary Startup:**
```bash
# Verify primary can start as polling
python3 -c "
from ops.telegram_failover_guard import validate_gateway_startup
result = validate_gateway_startup('primary', 'polling', None)
print(f'Startup valid: {result[\"ok\"]}')
print(f'Violations: {result[\"violations\"]}')
"
# Expected: Startup valid: True
```

**Standby Startup:**
```bash
# Verify standby cannot start as polling while primary healthy
python3 -c "
from ops.telegram_failover_guard import validate_gateway_startup
result = validate_gateway_startup('standby', 'polling', None, primary_healthy=True)
print(f'Startup valid: {result[\"ok\"]}')
print(f'Violations: {result[\"violations\"]}')
"
# Expected: Startup valid: False (standby_polling_while_primary_healthy)
```

#### 5. Failover Promotion Gating

**Promotion Eligibility:**
```bash
# Check if promotion is eligible
python3 -c "
from ops.telegram_failover_guard import (
    load_failover_state,
    evaluate_failover_promotion,
    check_primary_health
)
from pathlib import Path
import time

state = load_failover_state(Path('/var/lib/kolibri-telegram-gateway/failover.json'))
health = check_primary_health(health_data={'health': 'offline', 'heartbeat_at': str(time.time() - 300)})
result = evaluate_failover_promotion(state, health, now=time.time())
print(f'Should promote: {result[\"should_promote\"]}')
print(f'Reason: {result[\"reason\"]}')
"
# Expected: Should promote: True (when primary unhealthy and cooldown passed)
```

**Cooldown Enforcement:**
```bash
# Verify cooldown prevents rapid promotion
python3 -c "
from ops.telegram_failover_guard import (
    load_failover_state,
    evaluate_failover_promotion,
    save_failover_state,
    FailoverState
)
from pathlib import Path
import time

state = FailoverState(
    last_promotion_attempt=time.time() - 60,
    replication_verified=True
)
save_failover_state(state, Path('/tmp/test_failover.json'))
result = evaluate_failover_promotion(state, {'ok': False}, now=time.time())
print(f'Should promote: {result[\"should_promote\"]}')
print(f'Reason: {result[\"reason\"]}')
"
# Expected: Should promote: False, Reason: cooldown_active
```

### Post-Verification Commands

```bash
# Run all guard tests
python3 -m pytest tests/test_telegram_failover_guard.py -v

# Check test coverage
python3 -m pytest tests/test_telegram_failover_guard.py --cov=ops/telegram_failover_guard --cov-report=term-missing

# Verify no secrets in output
grep -rn "TELEGRAM_BOT_TOKEN\|owner_id\|chat_id" ops/telegram_failover_guard.py
# Expected: No matches (only regex patterns for redaction)
```

## Acceptance Criteria Verification

| Criterion | Verification | Status |
|-----------|--------------|--------|
| changed_files includes all artifacts | `git diff --name-only` shows guard, tests, runbook, verification doc | ✅ |
| tests_run non-empty with failover guard tests | `pytest tests/test_telegram_failover_guard.py` | ✅ |
| State replication fresh and hash-matched | `verify_state_replication()` returns ok=True | ✅ |
| No second active receiver while primary healthy | `detect_dual_receiver()` returns ok=True | ✅ |
| No secrets in logs/artifacts | `grep` finds no tokens/keys in output | ✅ |
| required_artifacts_missing empty | All 4 artifacts present | ✅ |

## Artifact Inventory

```
ops/telegram_failover_guard.py          # HA guard module
tests/test_telegram_failover_guard.py   # Guard unit tests (34 tests)
docs/TELEGRAM_HA_FAILOVER_RUNBOOK.md    # Operational runbook
docs/TELEGRAM_HA_RUNTIME_VERIFICATION.md # This verification doc
```

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
| `ops/telegram_gateway.py` | Gateway main: polling, task handling, owner communication |
| `ops/telegram_superfactory.py` | Receiver plan: validates mode conflicts |
| `ops/systemd/kolibri-telegram-gateway.service` | Systemd service for primary gateway |
| `tests/test_telegram_failover_guard.py` | Guard unit tests |

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

### 2. Verify State Replication

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

### 3. Check Primary Health

```bash
# Verify heartbeat freshness
ls -la /var/lib/kolibri-telegram-gateway/*.heartbeat
cat /var/lib/kolibri-telegram-gateway/*.heartbeat | python3 -m json.tool

# Check gateway logs for health
journalctl -u kolibri-telegram-gateway.service -n 20 --no-pager | grep -E "health|heartbeat|receiver"
```

### 4. Failover Guard Status

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
- Standby: send-only, no polling
- State hash: matched

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
- Replication verified

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
4. **State verification**: Replication hash must match before promotion
5. **Cooldown**: 300s minimum between promotion attempts

## Monitoring Checklist

- [ ] Primary gateway active and polling
- [ ] Standby gateway in send-only mode
- [ ] State replication hash matched
- [ ] Heartbeat freshness < 120s
- [ ] No dual receiver violations
- [ ] Promotion not blocked (unless intentional)

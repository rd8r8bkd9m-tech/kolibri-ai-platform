# Tests

All tests were read-only and bounded.

## Commands Run

```bash
git status --short
```

Result: clean before artifact creation.

```bash
ssh -o BatchMode=yes \
  -o PasswordAuthentication=no \
  -o KbdInteractiveAuthentication=no \
  -o PreferredAuthentications=publickey \
  -o ConnectTimeout=8 \
  -o ConnectionAttempts=1 \
  -o StrictHostKeyChecking=accept-new \
  hostvds-paris-highload '<read-only host/cpu/disk/api probe>'
```

Result: SSH timed out to `95.182.83.60:22`.

```bash
ssh -o BatchMode=yes \
  -o PasswordAuthentication=no \
  -o KbdInteractiveAuthentication=no \
  -o PreferredAuthentications=publickey \
  -o ConnectTimeout=8 \
  -o ConnectionAttempts=1 \
  -o StrictHostKeyChecking=accept-new \
  kolibri-primary-codex '<server-side Paris SSH reachability probe>'
```

Result: fallback host denied this worker key; no secret material printed.

```bash
python3 - <<'PY'
import urllib.request
for url in ["http://10.99.0.10:9101/health", "http://10.99.0.2:9101/health"]:
    with urllib.request.urlopen(url, timeout=8) as r:
        print(url, r.status, r.read().decode()[:300])
PY
```

Result: both Control Plane health endpoints returned HTTP 200.

```bash
python3 - <<'PY'
import json, urllib.request
for base in ["http://10.99.0.10:9101", "http://10.99.0.2:9101"]:
    with urllib.request.urlopen(base + "/v1/nodes", timeout=10) as r:
        data = json.load(r)
    # inspected only Paris/highload/mesh-agent-33 cards
PY
```

Result: `mesh-agent-33` fresh/online; Paris/highload target cards stale and missing resource stats.

```bash
curl -fsS --max-time 5 http://10.99.0.10:9101/health
curl -fsS --max-time 5 http://10.99.0.2:9101/health
df -hP / /var /tmp
df -ihP /
awk '/MemTotal|MemAvailable|SwapTotal|SwapFree/ {print}' /proc/meminfo
```

Result: assigned worker API routing and resource budget captured.

## Safety Checks

- No environment variables, private keys, tokens, or full process arguments were printed.
- No product code was modified.
- No destructive git command was run.
- No push, merge, deploy, restart, or credential change was attempted.


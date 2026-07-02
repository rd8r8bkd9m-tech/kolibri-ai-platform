# TESTS

Verification commands run:

```bash
git status --short --branch
hostname && whoami && git rev-parse --show-toplevel && git rev-parse --abbrev-ref HEAD && git rev-parse --short HEAD
ssh -o BatchMode=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no -o PreferredAuthentications=publickey -o ConnectTimeout=8 -o ConnectionAttempts=1 -o StrictHostKeyChecking=accept-new hostvds-agent-06 '...sanitized readiness probe...'
curl -fsS --max-time 8 http://10.99.0.2:9101/v1/health
curl -sS -D - --max-time 8 http://10.99.0.2:9101/health -o /tmp/kolibri-hostvds-agent-06-health-root.json
curl -fsS --max-time 8 http://10.99.0.2:9101/v1/nodes
curl -fsS --max-time 10 'http://10.99.0.2:9101/v1/fleet/route?target_node=hostvds-agent-06&required_capability=generic_implementation'
curl -fsS --max-time 10 'http://10.99.0.2:9101/v1/fabric/routes'
curl -fsS --max-time 10 'http://10.99.0.2:9101/v1/fabric/health'
curl -sS -D - --max-time 8 http://10.99.0.2:9101/v1/tasks -o /tmp/kolibri-hostvds-agent-06-tasks.json
python3 - <<'PY'
import json, pathlib
p=pathlib.Path('/tmp/kolibri-hostvds-agent-06-tasks.json')
obj=json.loads(p.read_text())
tasks=obj.get('tasks') or []
matches=[t.get('task_id') for t in tasks if 'hostvds-agent-06' in json.dumps(t) or 'agent-06' in json.dumps(t)]
print({'task_count': len(tasks), 'hostvds_agent_06_match_count': len(matches)})
PY
```

Observed results:

- `git status --short --branch`: clean before artifact creation.
- `GET /v1/health`: HTTP 200, Redis `PONG`, status `ok`.
- `GET /health`: HTTP 200, Redis `PONG`, status `ok`.
- `GET /v1/nodes`: timed out after 8 seconds.
- `GET /v1/fleet/route`: HTTP 404.
- `GET /v1/fabric/routes`: HTTP 404.
- `GET /v1/fabric/health`: HTTP 404.
- `GET /v1/tasks`: HTTP 200, task board available.
- SSH to `hostvds-agent-06`: TCP connection timed out before remote command
  execution, so disk, GitHub auth, and target runner health could not be proven.

# NEXT

Next exact task:

Deploy the scoped Home wallboard change on a host with Node 20.19+:

```bash
scripts/deploy-home-wallboard.sh deploy kolibri-main /opt/kolibri-ai
```

Then verify:

```bash
curl -fsS http://127.0.0.1:8000/api/factory/status | python3 -m json.tool | head -80
systemctl status kolibri-ai --no-pager
```

If `/v1/prs`, `/v1/blockers`, or `/v1/logs` are missing in Control Plane, add those read-only endpoints next so the wallboard PR/log/blocker sections become fully live instead of fallback/empty-state driven.


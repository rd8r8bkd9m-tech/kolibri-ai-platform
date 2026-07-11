# Vista OS — Release Runbook

## 1. Локальная проверка

```bash
./scripts/validate-fone.sh
./scripts/release-check.sh
```

## 2. Серверный запуск

```bash
cp .env.example .env
nano .env
./scripts/deploy-vista-server.sh
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/vista/release/readiness
```

## 3. Worker-node установка

```bash
sudo ./scripts/install-node.sh \
  --node-id server-002 \
  --control-url http://CONTROL_SERVER_IP:8000 \
  --join-token TOKEN \
  --signing-secret SECRET \
  --workers 2 \
  --capabilities health.probe,estimate.artifacts,factory.local
```

## 4. Проверка canary

```bash
VISTA_NODE_JOIN_TOKEN=TOKEN \
VISTA_NODE_SIGNING_SECRET=SECRET \
./scripts/run-factory-canary.sh --control-url http://CONTROL_SERVER_IP:8000
```

## 5. Rollback

```bash
docker compose down
# restore previous git tag / previous package
# restore vista-data volume backup when needed
```

## 6. Emergency pause

```bash
systemctl stop vista-node-agent
# or drain node through API:
curl -X POST http://CONTROL_SERVER_IP:8000/api/nodes/server-002/drain
```

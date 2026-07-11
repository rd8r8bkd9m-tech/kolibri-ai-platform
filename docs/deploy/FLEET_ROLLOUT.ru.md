# Раскатка Vista OS на fleet

## 1. Control Server

```bash
sudo apt update
sudo apt install -y git docker.io docker-compose-plugin

git clone -b фоне https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform.git /opt/vista
cd /opt/vista

export VISTA_NODE_JOIN_TOKEN='replace-with-long-token'
export VISTA_NODE_SIGNING_SECRET='replace-with-long-hmac-secret'
./scripts/deploy-vista-server.sh
```

## 2. Worker Node

```bash
sudo apt update
sudo apt install -y git python3

git clone -b фоне https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform.git /opt/vista
cd /opt/vista

sudo ./scripts/install-node.sh \
  --node-id server-002 \
  --control-url http://CONTROL_SERVER_IP:8000 \
  --join-token replace-with-long-token \
  --signing-secret replace-with-long-hmac-secret \
  --workers 2
```

## 3. Проверка

```bash
curl http://CONTROL_SERVER_IP:8000/api/fleet/health
curl http://CONTROL_SERVER_IP:8000/api/factory/stats
```

## 4. Drain node перед обслуживанием

```bash
curl -X POST http://CONTROL_SERVER_IP:8000/api/nodes/server-002/drain
```

Вернуть в работу:

```bash
curl -X POST http://CONTROL_SERVER_IP:8000/api/nodes/server-002/resume
```

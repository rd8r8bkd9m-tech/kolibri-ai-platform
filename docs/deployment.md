# Деплой Kolibri AI Platform

## Обзор

Платформа развернута на 6 выделенных серверах с WireGuard mesh-сетью.
Деплой выполняется через SSH с локальной машины или через GitHub Actions CI/CD.

## Серверы и SSH алиасы

| Сервер | Внешний IP | SSH | VPN IP | Роль |
|--------|-----------|-----|--------|------|
| Home | 178.207.11.90 | `kolibri-home` (порт 2222, user ladik) | 10.99.0.1 | Training, Redis |
| Main | 104.253.43.117 | `kolibri-main` | 10.99.0.2 | Gateway, Frontend |
| UIAP | 31.57.26.151 | `kolibri-uiap` | 10.99.0.3 | RAG Engine |
| QJNS | 217.60.63.97 | `kolibri-qjns` | 10.99.0.4 | Agent |
| 9FTS | 94.183.235.154 | `kolibri-9fts` | 10.99.0.5 | Inference |
| New (Joau) | 109.248.161.39 | `kolibri-new` | 10.99.0.6 | Worker |

## Скрипт деплоя

### deploy.sh

```bash
./scripts/deploy.sh <server>
```

Доступные серверы: `main`, `uiap`, `qjns`, `9fts`, `home`, `new`, `network`, `all`

- `network` — деплой на все серверы
- `all` — деплой на все серверы кроме 9fts

### auto-deploy.sh

Расширенный деплой с rollback, backup и health check:

```bash
./scripts/auto-deploy.sh <server>
```

Функции:
- Backup перед деплоем
- Автоматический rollback при failure
- Health check после деплоя
- Конфигурация через `infra/network/config.json`

## Деплой по серверам

### Main (API Gateway + Frontend)

```bash
# 1. Собрать frontend
cd frontend
npm run build
# → frontend/dist/

# 2. Скопировать на сервер
scp -r frontend/dist kolibri-main:/opt/kolibri-ai/frontend/
scp backend/*.py kolibri-main:/opt/kolibri-ai/backend/
scp backend/requirements.txt kolibri-main:/opt/kolibri-ai/backend/

# 3. На сервере
ssh kolibri-main
cd /opt/kolibri-ai/backend
pip install -r requirements.txt

# 4. Перезапустить сервис
sudo systemctl restart kolibri-ai
```

**Структура на сервере**:
```
/opt/kolibri-ai/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── auth.py
│   ├── providers.py
│   ├── pipeline.py
│   ├── routes_v1.py
│   ├── adapter.py
│   ├── health_checker.py
│   ├── logging_config.py
│   ├── tts.py
│   ├── stt.py
│   ├── websearch.py
│   └── requirements.txt
├── frontend/
│   └── dist/          # Production build
├── .env               # Environment variables
└── data/
    ├── kolibri.db     # SQLite
    └── tts/           # TTS audio files
```

### UIAP (RAG Engine)

```bash
scp infra/network/rag_service.py kolibri-uiap:/opt/kolibri-ai/rag/
ssh kolibri-uiap
sudo systemctl restart kolibri-rag
```

### QJNS (Agent)

```bash
scp infra/network/agent_service.py kolibri-qjns:/opt/kolibri-ai/agent/
ssh kolibri-qjns
sudo systemctl restart kolibri-agent
```

### Home (Redis + Organism)

```bash
scp infra/network/api.py kolibri-home:/opt/kolibri-ai/organism/
ssh kolibri-home
sudo systemctl restart kolibri-network
sudo systemctl restart redis
```

### New/Joau (Worker)

```bash
scp infra/network/api.py kolibri-new:/opt/kolibri-ai/organism/
scp infra/network/worker_service.py kolibri-new:/opt/kolibri-ai/worker/
ssh kolibri-new
sudo systemctl restart kolibri-network
```

## Systemd сервисы

### kolibri-ai.service (Main — Backend)

```ini
[Unit]
Description=Kolibri AI Backend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/kolibri-ai/backend
ExecStart=/usr/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
EnvironmentFile=/opt/kolibri-ai/.env

[Install]
WantedBy=multi-user.target
```

### kolibri-network.service (Home, New/Joau, Main — Organism)

```ini
[Unit]
Description=Kolibri Organism Agent
After=network.target redis.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/kolibri-ai/organism
ExecStart=/usr/bin/python3 -m uvicorn api:app --host 0.0.0.0 --port 9001
Restart=always
RestartSec=5
Environment=KOLIBRI_NODE=home
Environment=KOLIBRI_ROLE=training
Environment=KOLIBRI_PORT=9001
Environment=KOLIBRI_REDIS=10.99.0.1
Environment=KOLIBRI_REDIS_PORT=6379
Environment=KOLIBRI_GATEWAY=10.99.0.2

[Install]
WantedBy=multi-user.target
```

Переменные окружения для каждого сервера:

| Сервер | KOLIBRI_NODE | KOLIBRI_ROLE |
|--------|-------------|-------------|
| Home | home | training |
| Main | main | gateway |
| UIAP | uiap | rag |
| QJNS | qjns | agent |
| 9FTS | 9fts | inference |
| New | new | worker |

### kolibri-agent.service (QJNS)

```ini
[Unit]
Description=Kolibri Agent Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/kolibri-ai/agent
ExecStart=/usr/bin/python3 -m uvicorn agent_service:app --host 0.0.0.0 --port 8003
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### redis.service (Home)

```ini
[Unit]
Description=Redis Server
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/redis-server --bind 10.99.0.1 --port 6379 --daemonize no
Restart=always

[Install]
WantedBy=multi-user.target
```

## Nginx конфигурация (Main)

### Bare-metal конфигурация

```nginx
server {
    listen 80;
    server_name kolibri.ai;

    # Frontend
    location / {
        root /opt/kolibri-ai/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 600s;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
    }

    # Cluster (Organism)
    location /cluster/ {
        proxy_pass http://127.0.0.1:9001;
        proxy_set_header Host $host;
    }

    # Metrics
    location /metrics {
        proxy_pass http://127.0.0.1:8000;
    }
}
```

### Docker Compose конфигурация

При запуске через Docker Compose используются имена сервисов вместо 127.0.0.1:

```nginx
# Backend API
location /api/ {
    proxy_pass http://backend:8000;
    proxy_read_timeout 600s;
}

# Cluster (Organism)
location /cluster/ {
    proxy_pass http://organism:9001;
}
```

Полная Docker-конфигурация: `infra/network/nginx.conf`

Особенности Docker-конфигурации:
- `server_name _` (catch-all)
- Frontend root: `/usr/share/nginx/html`
- Gzip сжатие включено
- Security headers: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`
- Cache headers: `no-cache` для HTML, `1y immutable` для `/assets/`

## WireGuard конфигурация

Каждый сервер имеет WireGuard конфигурацию для mesh-сети.

**Порт**: 51830 (не 51820)

**Пример для Main (10.99.0.2)**:
```ini
[Interface]
PrivateKey = <MAIN_PRIVATE_KEY>
Address = 10.99.0.2/24
ListenPort = 51830

# Peer: Home
[Peer]
PublicKey = <HOME_PUBLIC_KEY>
AllowedIPs = 10.99.0.1/32
Endpoint = 178.207.11.90:51830
PersistentKeepalive = 25

# Peer: UIAP
[Peer]
PublicKey = <UIAP_PUBLIC_KEY>
AllowedIPs = 10.99.0.3/32
Endpoint = 31.57.26.151:51830
PersistentKeepalive = 25

# ... остальные пиры
```

Конфигурация VPN: `infra/network/config.json` (subnet, port, per-server settings).

## Docker Compose

6 сервисов для локальной разработки:

```yaml
services:
  redis:       # Redis 7 Alpine, port 6379
  backend:     # FastAPI app, port 8000, depends on redis
  frontend:    # Nginx + React SPA, port 80, depends on backend
  organism:    # Kolibri Organism, port 9001, depends on redis
  prometheus:  # Metrics collection, port 9090
  grafana:     # Dashboards, port 3000
```

Dockerfiles:
- `Dockerfile.backend` — Python 3.11-slim
- `Dockerfile.frontend` — Node 20 (build) + Nginx (serve)
- `Dockerfile.organism` — Python 3.11-slim

## CI/CD (GitHub Actions)

Pipeline: `.github/workflows/ci.yml`

**Триггер**: push в main/develop, PR в main.

### Этапы

| Job | Описание | Действия |
|-----|----------|----------|
| `lint` | Линтинг backend | `ruff check backend/` |
| `test` | Syntax check | `py_compile` на main.py, auth.py, config.py |
| `build-frontend` | Сборка фронта | `npm ci && npm run build`, upload artifact |
| `deploy` | Деплой на серверы | SSH deploy → Main, UIAP, QJNS, 9FTS |

### Deploy targets

CI/CD деплоит на 4 сервера:
- **Main**: backend + frontend (`kolibri-ai` service)
- **UIAP**: RAG service
- **QJNS**: Agent service (`kolibri-agent` service)
- **9FTS**: Inference service

Использует `root@<IP>` напрямую (не SSH алиасы).

## Infra Network Files

Директория `infra/network/` содержит:

| Файл | Описание |
|------|----------|
| `api.py` | Organism API сервер |
| `organism.py` | Organism logic |
| `agent_service.py` | Agent service (QJNS) |
| `rag_service.py` | RAG service (UIAP) |
| `worker_service.py` | Worker service (New/Joau) |
| `worker_setup.sh` | Worker setup script |
| `nginx.conf` | Nginx config (Docker) |
| `config.json` | Server config (IPs, ports, VPN) |
| `requirements.txt` | Python deps for network services |
| `rag_requirements.txt` | RAG-specific deps |

## Проверка состояния

```bash
# Проверить backend
curl http://104.253.43.117/api/health

# Проверить pipeline
curl http://104.253.43.117/api/pipeline/health

# Проверить Organism (Home)
curl http://178.207.11.90:9001/health

# Проверить кластер
curl http://178.207.11.90:9001/cluster/status

# Проверить метрики
curl http://104.253.43.117/metrics

# Проверить WireGuard
sudo wg show

# Проверить сервисы
sudo systemctl status kolibri-ai
sudo systemctl status kolibri-network
sudo systemctl status kolibri-agent
sudo systemctl status redis
```

## Логи

```bash
# Backend logs
sudo journalctl -u kolibri-ai -f

# Organism logs
sudo journalctl -u kolibri-network -f

# Agent logs
sudo journalctl -u kolibri-agent -f

# Redis logs
sudo journalctl -u redis -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

## Troubleshooting

### 9FTS (Inference) нестабилен
- Проверить: `curl http://94.183.235.154:8001/inference/health`
- Часто down из-за нехватки RAM (1.9GB)
- Pipeline автоматически фоллбэкит на прямой ответ

### Redis недоступен
- Все Organism ноды деградируют
- Проверить: `redis-cli -h 10.99.0.1 ping`
- Перезапустить: `sudo systemctl restart redis`

### Rate limit срабатывает
- 60 req/min per IP (настраивается через env)
- Очистить: `sqlite3 /opt/kolibri-ai/data/kolibri.db "DELETE FROM rate_limits;"`

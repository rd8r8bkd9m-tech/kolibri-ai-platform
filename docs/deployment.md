# Деплой Kolibri AI Platform

## Обзор

Платформа развернута на 6 выделенных серверах с WireGuard mesh-сетью.
Деплой выполняется через SSH с локальной машины.

## Серверы и SSH алиасы

| Сервер | Внешний IP | SSH | VPN IP | Роль |
|--------|-----------|-----|--------|------|
| Home | 178.207.11.90 | `ssh home` (порт 2222) | 10.99.0.1 | Training, Redis |
| Main | 104.253.43.117 | `ssh main` | 10.99.0.2 | Gateway, Frontend |
| UIAP | 31.57.26.151 | `ssh uiap` | 10.99.0.3 | RAG Engine |
| QJNS | 217.60.63.97 | `ssh qjns` | 10.99.0.4 | Agent |
| 9FTS | 94.183.235.154 | `ssh 9fts` | 10.99.0.5 | Inference |
| Joau | 109.248.161.39 | `ssh joau` | 10.99.0.6 | Worker |

## Скрипт деплоя

```bash
./scripts/deploy.sh <server>
```

Доступные серверы: `main`, `uiap`, `qjns`, `9fts`, `home`, `joau`

## Деплой по серверам

### Main (API Gateway + Frontend)

```bash
# 1. Собрать frontend
cd frontend
npm run build
# → frontend/dist/

# 2. Скопировать на сервер
scp -r frontend/dist main:/opt/kolibri-ai/frontend/
scp backend/*.py main:/opt/kolibri-ai/backend/
scp backend/requirements.txt main:/opt/kolibri-ai/backend/

# 3. На сервере
ssh main
cd /opt/kolibri-ai/backend
pip install -r requirements.txt

# 4. Перезапустить сервис
sudo systemctl restart kolibri-backend
```

**Структура на сервере**:
```
/opt/kolibri-ai/
├── backend/
│   ├── main.py
│   ├── routes_v1.py
│   ├── pipeline.py
│   ├── providers.py
│   ├── tts.py
│   ├── stt.py
│   ├── websearch.py
│   └── requirements.txt
├── frontend/
│   └── dist/          # Production build
└── data/
    ├── kolibri.db     # SQLite
    └── tts/           # TTS audio files
```

### UIAP (RAG Engine)

```bash
scp infra/network/rag_server.py uiap:/opt/kolibri-ai/rag/
ssh uiap
sudo systemctl restart kolibri-rag
```

### QJNS (Agent)

```bash
scp infra/network/agent_server.py qjns:/opt/kolibri-ai/agent/
ssh qjns
sudo systemctl restart kolibri-agent
```

### Home (Redis + Organism)

```bash
scp infra/network/api.py home:/opt/kolibri-ai/organism/
ssh home
sudo systemctl restart kolibri-organism
sudo systemctl restart redis
```

### Joau (Worker)

```bash
scp infra/network/api.py joau:/opt/kolibri-ai/organism/
ssh joau
sudo systemctl restart kolibri-organism
```

## Systemd сервисы

### kolibri-backend.service (Main)

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
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

### kolibri-organism.service (Home, Joau, и др.)

```ini
[Unit]
Description=Kolibri Organism Agent
After=network.target redis.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/kolibri-ai/organism
ExecStart=/usr/bin/python3 api.py
Restart=always
RestartSec=5
Environment=KOLIBRI_NODE=home
Environment=KOLIBRI_ROLE=training
Environment=KOLIBRI_PORT=9001
Environment=KOLIBRI_REDIS=10.99.0.1
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
| Joau | joau | worker |

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
        proxy_read_timeout 120s;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    # Cluster (Organism)
    location /cluster/ {
        proxy_pass http://127.0.0.1:9001;
        proxy_set_header Host $host;
    }
}
```

## WireGuard конфигурация

Каждый сервер имеет WireGuard конфигурацию для mesh-сети.

**Пример для Main (10.99.0.2)**:
```ini
[Interface]
PrivateKey = <MAIN_PRIVATE_KEY>
Address = 10.99.0.2/24
ListenPort = 51820

# Peer: Home
[Peer]
PublicKey = <HOME_PUBLIC_KEY>
AllowedIPs = 10.99.0.1/32
Endpoint = 178.207.11.90:51820
PersistentKeepalive = 25

# Peer: UIAP
[Peer]
PublicKey = <UIAP_PUBLIC_KEY>
AllowedIPs = 10.99.0.3/32
Endpoint = 31.57.26.151:51820
PersistentKeepalive = 25

# ... остальные пиры
```

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

# Проверить WireGuard
sudo wg show

# Проверить сервисы
sudo systemctl status kolibri-backend
sudo systemctl status kolibri-organism
sudo systemctl status redis
```

## Логи

```bash
# Backend logs
sudo journalctl -u kolibri-backend -f

# Organism logs
sudo journalctl -u kolibri-organism -f

# Redis logs
sudo journalctl -u redis -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

## Troubleshooting

### 9FTS (Inference) нестабилен
- Проверить: `curl http://94.183.235.154:8001/inference/health`
- Часто down из-за нехватки RAM
- Pipeline автоматически фоллбэкит на прямой ответ

### Redis недоступен
- Все Organism ноды деградируют
- Проверить: `redis-cli -h 10.99.0.1 ping`
- Перезапустить: `sudo systemctl restart redis`

### Rate limit срабатывает
- 60 req/min per IP
- Очистить: `sqlite3 /opt/kolibri-ai/data/kolibri.db "DELETE FROM rate_limits;"`

# Vista OS 11.1 — production deployment

## 1. Подготовить сервер

Минимум: Ubuntu 24.04 LTS, Docker Engine и Docker Compose v2, 4 CPU, 8 ГБ RAM, 40 ГБ SSD.

```bash
git clone <repository-url> /opt/vista
cd /opt/vista
cp .env.example .env
```

Создайте каждый секрет отдельно:

```bash
openssl rand -hex 32
```

Заполните `.env`. Не используйте примеры из `.env.example` в production.

## 2. Проверить release candidate

```bash
python3 -m pip install -r backend/requirements-dev.txt
./scripts/validate-fone.sh
./scripts/release-check.sh
```

## 3. Запустить

```bash
./scripts/deploy-vista-server.sh
```

Backend слушает только `127.0.0.1:8000`. Frontend доступен на `:8080`. Перед публичным запуском поставьте TLS reverse proxy (Caddy, Nginx или ingress) и направьте `/api/*` и `/v1/*` на backend.

## 4. Worker-ноды

```bash
sudo ./scripts/install-node.sh \
  --node-id worker-01 \
  --control-url https://vista.example.com \
  --join-token "$VISTA_NODE_JOIN_TOKEN" \
  --signing-secret "$VISTA_NODE_SIGNING_SECRET" \
  --workers 2 \
  --capabilities health.probe,estimate.artifacts
```

Перед заявлением о работе фабрики 24/7 выполните live canary на Control Plane и минимум двух независимых worker-нодах.

## 5. Backup

Данные находятся в Docker volume `vista-data`: SQLite database и каталог артефактов. Выполняйте регулярный snapshot volume и проверяйте восстановление командой `tools/backup_restore_check.py`.

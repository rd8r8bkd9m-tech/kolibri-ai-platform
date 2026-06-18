#!/bin/bash
# Kolibri AI - Automated Backup Script
# Usage: ./backup.sh [full|db|configs]

set -e

BACKUP_DIR="/opt/kolibri-ai/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DATA_DIR="/opt/kolibri-ai/data"
CONFIG_DIR="/opt/kolibri-ai"

mkdir -p "$BACKUP_DIR"

backup_db() {
    echo "Backing up SQLite database..."
    if [ -f "$DATA_DIR/kolibri.db" ]; then
        cp "$DATA_DIR/kolibri.db" "$BACKUP_DIR/kolibri_${DATE}.db"
        gzip "$BACKUP_DIR/kolibri_${DATE}.db"
        echo "Database backup: kolibri_${DATE}.db.gz"
    else
        echo "Warning: Database not found at $DATA_DIR/kolibri.db"
    fi
}

backup_configs() {
    echo "Backing up configuration files..."
    tar -czf "$BACKUP_DIR/configs_${DATE}.tar.gz" \
        -C "$CONFIG_DIR" \
        .env \
        backend/config.py \
        2>/dev/null || echo "Warning: Some config files not found"
    echo "Config backup: configs_${DATE}.tar.gz"
}

backup_documents() {
    echo "Backing up generated documents..."
    if [ -d "$DATA_DIR/documents" ]; then
        tar -czf "$BACKUP_DIR/documents_${DATE}.tar.gz" -C "$DATA_DIR" documents/
        echo "Documents backup: documents_${DATE}.tar.gz"
    fi
}

backup_redis() {
    echo "Backing up Redis data..."
    if command -v redis-cli &> /dev/null; then
        redis-cli -h 10.99.0.1 BGSAVE 2>/dev/null || true
        sleep 2
        if [ -f "/var/lib/redis/dump.rdb" ]; then
            cp "/var/lib/redis/dump.rdb" "$BACKUP_DIR/redis_${DATE}.rdb"
            gzip "$BACKUP_DIR/redis_${DATE}.rdb"
            echo "Redis backup: redis_${DATE}.rdb.gz"
        fi
    fi
}

cleanup_old_backups() {
    echo "Cleaning up backups older than 30 days..."
    find "$BACKUP_DIR" -type f -mtime +30 -delete 2>/dev/null || true
}

case "${1:-full}" in
    db)
        backup_db
        ;;
    configs)
        backup_configs
        ;;
    full)
        backup_db
        backup_configs
        backup_documents
        backup_redis
        ;;
    *)
        echo "Usage: $0 [full|db|configs]"
        exit 1
        ;;
esac

cleanup_old_backups
echo "Backup completed at $(date)"

#!/bin/bash
# Kolibri AI — Auto Deploy with rollback
# Usage: ./scripts/auto-deploy.sh <server|all> [--rollback]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$PROJECT_DIR/infra/network/config.json"
DEPLOY_LOG="$PROJECT_DIR/logs/deploy"
mkdir -p "$DEPLOY_LOG"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SERVERS=("home" "main" "uiap" "qjns" "9fts" "kolibri")
ROLLBACK=false
TARGET=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --rollback) ROLLBACK=true; shift ;;
        *) TARGET="$1"; shift ;;
    esac
done

get_server_info() {
    python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['servers']['$1']['$2'])" 2>/dev/null
}

ssh_exec() {
    local server="$1"; shift
    local alias
    alias=$(get_server_info "$server" "ssh_alias")
    ssh -o ConnectTimeout=10 "$alias" "$*" 2>/dev/null
}

backup_before_deploy() {
    local server="$1"
    local alias
    alias=$(get_server_info "$server" "ssh_alias")
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_dir="/opt/kolibri-ai/backups/pre-deploy"
    
    ssh_exec "$server" "mkdir -p $backup_dir"
    
    case "$server" in
        main)
            ssh_exec "$server" "cp -r /opt/kolibri-ai/backend $backup_dir/backend_$timestamp 2>/dev/null || true"
            ssh_exec "$server" "cp /opt/kolibri-ai/data/kolibri.db $backup_dir/kolibri_db_$timestamp.sqlite3 2>/dev/null || true"
            ;;
        uiap|qjns)
            ssh_exec "$server" "cp /opt/kolibri-ai/network/api.py $backup_dir/api_$timestamp.py 2>/dev/null || true"
            ;;
        9fts)
            ssh_exec "$server" "cp /opt/kolibri-ai/inference/api.py $backup_dir/api_$timestamp.py 2>/dev/null || true"
            ;;
    esac
    
    echo "$timestamp" > "$DEPLOY_LOG/${server}_last_backup.txt"
    log "Backed up $server state at $timestamp"
}

rollback_server() {
    local server="$1"
    local alias
    alias=$(get_server_info "$server" "ssh_alias")
    local last_backup
    last_backup=$(cat "$DEPLOY_LOG/${server}_last_backup.txt" 2>/dev/null || echo "")
    
    if [ -z "$last_backup" ]; then
        echo -e "${RED}[$server]${NC} No backup found for rollback"
        return 1
    fi
    
    local backup_dir="/opt/kolibri-ai/backups/pre-deploy"
    echo -e "${YELLOW}[$server]${NC} Rolling back to $last_backup..."
    
    case "$server" in
        main)
            ssh_exec "$server" "cp -r $backup_dir/backend_$last_backup/* /opt/kolibri-ai/backend/ 2>/dev/null && systemctl restart kolibri-ai"
            ;;
        uiap|qjns)
            ssh_exec "$server" "cp $backup_dir/api_$last_backup.py /opt/kolibri-ai/network/api.py 2>/dev/null && systemctl restart kolibri-network"
            ;;
        9fts)
            ssh_exec "$server" "cp $backup_dir/api_$last_backup.py /opt/kolibri-ai/inference/api.py 2>/dev/null && systemctl restart kolibri-inference"
            ;;
    esac
    
    echo -e "${GREEN}[$server]${NC} Rollback complete"
}

deploy_server() {
    local server="$1"
    local alias
    alias=$(get_server_info "$server" "ssh_alias")
    
    echo -e "${BLUE}[$server]${NC} Deploying..."
    
    # Backup before deploy
    backup_before_deploy "$server"
    
    case "$server" in
        main)
            # Build frontend locally
            echo -e "${YELLOW}[$server]${NC} Building frontend..."
            (cd "$PROJECT_DIR/frontend" && npm run build 2>/dev/null) || { echo -e "${RED}[$server]${NC} Frontend build failed"; return 1; }
            
            # Copy files
            scp -r "$PROJECT_DIR/backend/" "$alias:/opt/kolibri-ai/backend/" 2>/dev/null
            scp -r "$PROJECT_DIR/frontend/dist/" "$alias:/opt/kolibri-ai/frontend/dist/" 2>/dev/null
            
            # Restart services
            ssh_exec "$server" "systemctl restart kolibri-ai && nginx -t && systemctl reload nginx"
            ;;
        uiap|qjns)
            scp "$PROJECT_DIR/infra/network/api.py" "$alias:/opt/kolibri-ai/network/api.py" 2>/dev/null
            ssh_exec "$server" "systemctl restart kolibri-network"
            ;;
        9fts)
            scp "$PROJECT_DIR/infra/inference/api.py" "$alias:/opt/kolibri-ai/inference/api.py" 2>/dev/null
            ssh_exec "$server" "systemctl restart kolibri-inference"
            ;;
        home)
            scp -r "$PROJECT_DIR/scripts/training/" "$alias:/opt/kolibri-ai/training/" 2>/dev/null || true
            ;;
        kolibri)
            scp "$PROJECT_DIR/infra/network/worker_service.py" "$alias:/opt/kolibri-ai/network/worker_service.py" 2>/dev/null
            ssh_exec "$server" "systemctl restart kolibri-worker"
            ;;
    esac
    
    # Verify
    sleep 3
    if [ "$server" = "main" ]; then
        local code
        code=$(ssh_exec "$server" "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/health")
        if [ "$code" = "200" ]; then
            echo -e "${GREEN}[$server]${NC} Deployed & verified ✓"
        else
            echo -e "${RED}[$server]${NC} Deployed but health check failed (HTTP $code)"
            echo -e "${YELLOW}[$server]${NC} Run with --rollback to revert"
        fi
    else
        echo -e "${GREEN}[$server]${NC} Deployed ✓"
    fi
}

log() { echo "[$(date -Iseconds)] $*" >> "$DEPLOY_LOG/deploy.log"; }

# ── Main ────────────────────────────────────────────────────────────────
if [ -z "$TARGET" ]; then
    echo "Usage: $0 <server|all> [--rollback]"
    echo "Servers: ${SERVERS[*]}"
    exit 1
fi

if [ "$ROLLBACK" = true ]; then
    echo -e "${YELLOW}=== Rolling back ===${NC}"
    if [ "$TARGET" = "all" ]; then
        for s in "${SERVERS[@]}"; do rollback_server "$s" || true; done
    else
        rollback_server "$TARGET"
    fi
else
    echo -e "${BLUE}=== Deploying ===${NC}"
    log "Deploy started: target=$TARGET"
    if [ "$TARGET" = "all" ]; then
        for s in "${SERVERS[@]}"; do deploy_server "$s" || true; done
    else
        deploy_server "$TARGET"
    fi
    log "Deploy completed"
fi

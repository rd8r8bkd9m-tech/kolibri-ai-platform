#!/bin/bash
# Kolibri AI — AI Task Orchestration
# Run MiMo AI tasks on servers with progress tracking
# Usage: ./scripts/ai-tasks.sh <task> [server|all] [args...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$PROJECT_DIR/infra/network/config.json"
TASK_LOG="$PROJECT_DIR/logs/ai-tasks"
mkdir -p "$TASK_LOG"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

get_server_info() {
    python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['servers']['$1']['$2'])" 2>/dev/null
}

ssh_exec() {
    local server="$1"; shift
    local alias
    alias=$(get_server_info "$server" "ssh_alias")
    local port=""
    if [ "$server" = "home" ]; then port="-p 2222"; fi
    ssh -o ConnectTimeout=10 $port "$alias" "$*" 2>/dev/null
}

run_ai_task() {
    local server="$1"
    local prompt="$2"
    local mimo_path
    mimo_path=$(get_server_info "$server" "mimo_path")
    local role
    role=$(get_server_info "$server" "role")
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local log_file="$TASK_LOG/${server}_${timestamp}.log"
    
    echo -e "${BLUE}[$server]${NC} Role: $role"
    echo -e "${BLUE}[$server]${NC} Task: ${prompt:0:80}..."
    
    ssh_exec "$server" "$mimo_path run --dangerously-skip-permissions --model mimo/mimo-auto '$prompt'" 2>&1 | tee "$log_file"
    
    local exit_code=${PIPESTATUS[0]}
    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}[$server]${NC} Task completed ✓ Log: $log_file"
    else
        echo -e "${RED}[$server]${NC} Task failed (exit $exit_code) Log: $log_file"
    fi
    return $exit_code
}

# ── Predefined tasks ──────────────────────────────────────────────────

task_security_audit() {
    local server="$1"
    run_ai_task "$server" "Run a security audit on this server. Check: 1) Open ports (ss -tlnp), 2) Failed SSH logins (journalctl -u sshd), 3) Unusual processes, 4) File permissions on /opt/kolibri-ai, 5) Firewall rules. Report findings and fix any issues."
}

task_cleanup() {
    local server="$1"
    run_ai_task "$server" "Clean up this server: 1) Remove old logs (journalctl --vacuum-time=7d), 2) Clean apt cache, 3) Remove unused Docker images, 4) Clean /tmp, 5) Report freed space."
}

task_update_packages() {
    local server="$1"
    run_ai_task "$server" "Update system packages: 1) apt update, 2) apt upgrade -y (skip if interactive), 3) Check if reboot needed, 4) Report updated packages. Do NOT reboot automatically."
}

task_check_services() {
    local server="$1"
    run_ai_task "$server" "Check all kolibri services on this server: 1) List running services, 2) Check logs for errors (last 100 lines), 3) Check resource usage, 4) Verify network connectivity to other nodes via VPN (ping 10.99.0.1-6), 5) Report status."
}

task_optimize_db() {
    run_ai_task "main" "Optimize the SQLite database: 1) Run VACUUM on /opt/kolibri-ai/data/kolibri.db, 2) Run ANALYZE, 3) Check integrity, 4) Report database size before and after."
}

task_backup_verify() {
    local server="${1:-main}"
    run_ai_task "$server" "Verify backups: 1) List recent backups in /opt/kolibri-ai/backups/, 2) Check backup sizes are reasonable, 3) Test restore of latest SQLite backup to /tmp/test_restore.db, 4) Report status."
}

# ── Usage ─────────────────────────────────────────────────────────────

usage() {
    cat <<EOF
Kolibri AI — AI Task Orchestration

Usage: $0 <task> [server|all]

Tasks:
  security <server>     Security audit
  cleanup <server>      Clean up disk space
  update <server>       Update system packages
  services <server>     Check kolibri services
  optimize-db           Optimize SQLite database (main)
  backup-verify <srv>   Verify backup integrity
  custom <server> "..."  Run custom prompt on server
  parallel "..."         Run task on all servers

Examples:
  $0 security main
  $0 cleanup all
  $0 custom uiap "Rebuild ChromaDB index"
  $0 parallel "Check disk space and report"
EOF
}

# ── Main ────────────────────────────────────────────────────────────────

TASK="${1:-help}"
SERVER="${2:-}"
shift 2 2>/dev/null || true
EXTRA_ARGS="$*"

case "$TASK" in
    security)
        [ -z "$SERVER" ] && { echo "Server required"; exit 1; }
        if [ "$SERVER" = "all" ]; then
            for s in home main uiap qjns 9fts kolibri; do task_security_audit "$s" || true; done
        else
            task_security_audit "$SERVER"
        fi
        ;;
    cleanup)
        [ -z "$SERVER" ] && { echo "Server required"; exit 1; }
        if [ "$SERVER" = "all" ]; then
            for s in home main uiap qjns 9fts kolibri; do task_cleanup "$s" || true; done
        else
            task_cleanup "$SERVER"
        fi
        ;;
    update)
        [ -z "$SERVER" ] && { echo "Server required"; exit 1; }
        if [ "$SERVER" = "all" ]; then
            for s in home main uiap qjns 9fts kolibri; do task_update_packages "$s" || true; done
        else
            task_update_packages "$SERVER"
        fi
        ;;
    services)
        [ -z "$SERVER" ] && { echo "Server required"; exit 1; }
        if [ "$SERVER" = "all" ]; then
            for s in home main uiap qjns 9fts kolibri; do task_check_services "$s" || true; done
        else
            task_check_services "$SERVER"
        fi
        ;;
    optimize-db)
        task_optimize_db
        ;;
    backup-verify)
        task_backup_verify "${SERVER:-main}"
        ;;
    custom)
        [ -z "$SERVER" ] && { echo "Server required"; exit 1; }
        run_ai_task "$SERVER" "$EXTRA_ARGS"
        ;;
    parallel)
        [ -z "$SERVER" ] && { echo "Prompt required"; exit 1; }
        PROMPT="$SERVER $EXTRA_ARGS"
        for s in home main uiap qjns 9fts kolibri; do
            (run_ai_task "$s" "$PROMPT") &
        done
        wait
        ;;
    help|*)
        usage
        ;;
esac

#!/bin/bash
# Kolibri AI — Cron Job Setup
# Installs monitoring, backup, and maintenance cron jobs
# Usage: ./scripts/setup-cron.sh [--remove]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CRON_TAG="# kolibri-ai-automation"

REMOVE=false
[[ "${1:-}" == "--remove" ]] && REMOVE=true

log() { echo "[$(date -Iseconds)] $*"; }

if [ "$REMOVE" = true ]; then
    log "Removing Kolibri AI cron jobs..."
    crontab -l 2>/dev/null | grep -v "$CRON_TAG" | crontab -
    log "Done."
    exit 0
fi

log "Installing Kolibri AI cron jobs..."

# Build the cron entries
CRON_ENTRIES="
# ── Kolibri AI Automation ──────────────────────────────────────$CRON_TAG

# Health monitoring — every 5 minutes
*/5 * * * * $SCRIPT_DIR/monitor.sh --alert-webhook \${KOLIBRI_WEBHOOK_URL:-} >> $PROJECT_DIR/logs/monitor/cron.log 2>&1 $CRON_TAG

# Daily backup — 3:00 AM
0 3 * * * $SCRIPT_DIR/backup.sh daily >> $PROJECT_DIR/logs/backup/daily.log 2>&1 $CRON_TAG

# Weekly backup — Sunday 4:00 AM
0 4 * * 0 $SCRIPT_DIR/backup.sh weekly >> $PROJECT_DIR/logs/backup/weekly.log 2>&1 $CRON_TAG

# Database optimization — Saturday 5:00 AM
0 5 * * 6 $SCRIPT_DIR/ai-tasks.sh optimize-db >> $PROJECT_DIR/logs/ai-tasks/optimize.log 2>&1 $CRON_TAG

# Security audit — Monday 6:00 AM
0 6 * * 1 $SCRIPT_DIR/ai-tasks.sh security main >> $PROJECT_DIR/logs/ai-tasks/security.log 2>&1 $CRON_TAG

# Disk cleanup — Wednesday 3:30 AM
30 3 * * 3 $SCRIPT_DIR/ai-tasks.sh cleanup main >> $PROJECT_DIR/logs/ai-tasks/cleanup.log 2>&1 $CRON_TAG

# Log rotation cleanup — daily 2:00 AM
0 2 * * * find $PROJECT_DIR/logs -name '*.log' -mtime +30 -delete 2>/dev/null $CRON_TAG
"

# Create log directories
mkdir -p "$PROJECT_DIR/logs/monitor" "$PROJECT_DIR/logs/backup" "$PROJECT_DIR/logs/ai-tasks"

# Install cron jobs (preserve existing)
EXISTING=$(crontab -l 2>/dev/null | grep -v "$CRON_TAG" || true)
echo "${EXISTING}${CRON_ENTRIES}" | crontab -

log "Cron jobs installed. Current crontab:"
crontab -l | grep "$CRON_TAG" | grep -v "^#"

echo ""
echo "Installed jobs:"
echo "  */5 min  — Health monitoring + auto-restart"
echo "  3:00 AM  — Daily backup (SQLite + ChromaDB)"
echo "  Sun 4AM  — Weekly backup (30 day retention)"
echo "  Sat 5AM  — Database optimization"
echo "  Mon 6AM  — Security audit (main server)"
echo "  Wed 3AM  — Disk cleanup (main server)"
echo "  2:00 AM  — Old log cleanup (30+ days)"
echo ""
echo "Configure alerts:"
echo "  export TELEGRAM_BOT_TOKEN=<token>"
echo "  export TELEGRAM_CHAT_ID=<chat_id>"
echo "  export KOLIBRI_WEBHOOK_URL=<webhook_url>"

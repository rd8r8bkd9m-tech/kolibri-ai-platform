#!/bin/bash
# Kolibri AI — Cluster Monitoring & Alerts
# Checks all services, sends alerts on failure
# Usage: ./scripts/monitor.sh [--alert-telegram] [--alert-webhook URL]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$PROJECT_DIR/infra/network/config.json"
STATE_DIR="$PROJECT_DIR/logs/monitor"
mkdir -p "$STATE_DIR"

ALERT_TELEGRAM=false
ALERT_WEBHOOK=""
ALERT_FILE="$STATE_DIR/alerts.log"
HEALTH_FILE="$STATE_DIR/health.json"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --alert-telegram) ALERT_TELEGRAM=true; shift ;;
        --alert-webhook) ALERT_WEBHOOK="$2"; shift 2 ;;
        *) shift ;;
    esac
done

log() { echo "[$(date -Iseconds)] $*"; }

send_alert() {
    local level="$1" server="$2" message="$3"
    local ts=$(date -Iseconds)
    local alert_msg="[$level] $server: $message"
    echo "$ts $alert_msg" >> "$ALERT_FILE"
    log "ALERT: $alert_msg"

    if [ "$ALERT_TELEGRAM" = true ] && [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
        curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d chat_id="$TELEGRAM_CHAT_ID" \
            -d text="🚨 Kolibri AI: $alert_msg" \
            -d parse_mode="HTML" >/dev/null 2>&1 || true
    fi

    if [ -n "$ALERT_WEBHOOK" ]; then
        curl -s -X POST "$ALERT_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "{\"level\":\"$level\",\"server\":\"$server\",\"message\":\"$message\",\"timestamp\":\"$ts\"}" >/dev/null 2>&1 || true
    fi
}

check_service() {
    local server="$1"
    local alias
    alias=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['servers']['$server']['ssh_alias'])" 2>/dev/null)

    if [ -z "$alias" ]; then return 1; fi

    # Check SSH connectivity
    if ! ssh -o ConnectTimeout=5 "$alias" "echo ok" >/dev/null 2>&1; then
        send_alert "CRITICAL" "$server" "SSH unreachable"
        return 1
    fi

    # Check kolibri services
    local services
    services=$(python3 -c "import json; s=json.load(open('$CONFIG_FILE'))['servers']['$server'].get('services',[]); print(' '.join(s))" 2>/dev/null || echo "")

    if [ -n "$services" ]; then
        for svc in $services; do
            local status
            status=$(ssh -o ConnectTimeout=5 "$alias" "systemctl is-active $svc 2>/dev/null" || echo "unknown")
            if [ "$status" != "active" ]; then
                send_alert "CRITICAL" "$server" "Service $svc is $status"
                # Auto-restart
                log "Auto-restarting $svc on $server..."
                ssh -o ConnectTimeout=5 "$alias" "systemctl restart $svc" 2>/dev/null || true
                sleep 3
                local new_status
                new_status=$(ssh -o ConnectTimeout=5 "$alias" "systemctl is-active $svc 2>/dev/null" || echo "unknown")
                if [ "$new_status" = "active" ]; then
                    send_alert "INFO" "$server" "Service $svc auto-restarted successfully"
                else
                    send_alert "CRITICAL" "$server" "Service $svc failed to restart"
                fi
            fi
        done
    fi

    # Check disk space
    local disk_usage
    disk_usage=$(ssh -o ConnectTimeout=5 "$alias" "df -h / | awk 'NR==2{print \$5}' | tr -d '%'" 2>/dev/null || echo "0")
    if [ "$disk_usage" -gt 90 ]; then
        send_alert "WARNING" "$server" "Disk usage at ${disk_usage}%"
    fi

    # Check memory
    local mem_usage
    mem_usage=$(ssh -o ConnectTimeout=5 "$alias" "free | awk '/Mem:/{printf \"%d\", \$3/\$2*100}'" 2>/dev/null || echo "0")
    if [ "$mem_usage" -gt 90 ]; then
        send_alert "WARNING" "$server" "Memory usage at ${mem_usage}%"
    fi

    # Check API health endpoint (for main)
    if [ "$server" = "main" ]; then
        local http_code
        http_code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 "http://127.0.0.1:8000/api/health" 2>/dev/null || echo "000")
        # Run via SSH since we check from local
        http_code=$(ssh -o ConnectTimeout=5 "$alias" "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/health" 2>/dev/null || echo "000")
        if [ "$http_code" != "200" ]; then
            send_alert "CRITICAL" "$server" "API health check failed (HTTP $http_code)"
        fi
    fi

    return 0
}

# ── Main ────────────────────────────────────────────────────────────────
log "Starting cluster health check..."

SERVERS=("home" "main" "uiap" "qjns" "9fts" "kolibri")
ONLINE=0
TOTAL=${#SERVERS[@]}

echo '{"timestamp":"'$(date -Iseconds)'","servers":{' > "$HEALTH_FILE.tmp"
first=true

for server in "${SERVERS[@]}"; do
    if check_service "$server"; then
        ONLINE=$((ONLINE + 1))
        status="ok"
    else
        status="fail"
    fi
    if [ "$first" = true ]; then first=false; else echo ',' >> "$HEALTH_FILE.tmp"; fi
    echo "\"$server\":{\"status\":\"$status\"}" >> "$HEALTH_FILE.tmp"
done

echo '}}' >> "$HEALTH_FILE.tmp"
mv "$HEALTH_FILE.tmp" "$HEALTH_FILE"

log "Health check complete: $ONLINE/$TOTAL servers online"

if [ "$ONLINE" -lt "$TOTAL" ]; then
    send_alert "WARNING" "cluster" "$(($TOTAL - ONLINE)) server(s) unreachable"
fi

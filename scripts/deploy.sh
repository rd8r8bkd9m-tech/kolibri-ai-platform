#!/bin/bash
# Kolibri AI Platform — Deploy script
# Usage: ./scripts/deploy.sh [main|uiap|qjns|9fts|home|agent-host|all]

set -e

SERVER=${1:-all}
SSH_TIMEOUT=10
AGENT_HOST_TARGET=${AGENT_HOST_TARGET:-kolibri-main}
AGENT_HOST_REPO=${AGENT_HOST_REPO:-/opt/kolibri-ai-platform}
AGENT_HOST_LAUNCHER=${AGENT_HOST_LAUNCHER:-/usr/local/bin/kolibri-agent-host}
AGENT_HOST_SERVICE=${AGENT_HOST_SERVICE:-kolibri-agent-host.service}

deploy_main() {
    echo "=== Deploying Main (API Gateway + Frontend) ==="
    scp -r -o ConnectTimeout=$SSH_TIMEOUT backend/ kolibri-main:/opt/kolibri-ai/
    scp -r -o ConnectTimeout=$SSH_TIMEOUT frontend/src/ kolibri-main:/opt/kolibri-ai/frontend/
    scp -o ConnectTimeout=$SSH_TIMEOUT frontend/package.json kolibri-main:/opt/kolibri-ai/frontend/
    scp -o ConnectTimeout=$SSH_TIMEOUT frontend/vite.config.js kolibri-main:/opt/kolibri-ai/frontend/
    scp -o ConnectTimeout=$SSH_TIMEOUT frontend/index.html kolibri-main:/opt/kolibri-ai/frontend/
    ssh -o ConnectTimeout=$SSH_TIMEOUT kolibri-main "cd /opt/kolibri-ai/frontend && npm run build 2>&1 && systemctl restart kolibri-ai && nginx -t && systemctl reload nginx"
    echo "Main deployed ✓"
}

deploy_uiap() {
    echo "=== Deploying UIAP (RAG Engine) ==="
    scp -o ConnectTimeout=$SSH_TIMEOUT infra/network/api.py kolibri-uiap:/opt/kolibri-network/
    ssh -o ConnectTimeout=$SSH_TIMEOUT kolibri-uiap "systemctl restart kolibri-network"
    echo "UIAP deployed ✓"
}

deploy_qjns() {
    echo "=== Deploying QJNS (Agent) ==="
    scp -o ConnectTimeout=$SSH_TIMEOUT infra/network/api.py kolibri-qjns:/opt/kolibri-network/
    ssh -o ConnectTimeout=$SSH_TIMEOUT kolibri-qjns "systemctl restart kolibri-network"
    echo "QJNS deployed ✓"
}

deploy_9fts() {
    echo "=== Deploying 9FTS (Inference) ==="
    scp -o ConnectTimeout=$SSH_TIMEOUT infra/inference/api.py kolibri-9fts:/opt/kolibri-inference/
    ssh -o ConnectTimeout=$SSH_TIMEOUT kolibri-9fts "systemctl restart kolibri-inference"
    echo "9FTS deployed ✓"
}

deploy_home() {
    echo "=== Deploying Home (Training Hub) ==="
    scp -r -o ConnectTimeout=$SSH_TIMEOUT -P 2222 scripts/training/ ladik@178.207.11.90:/home/ladik/kolibri-training/
    echo "Home deployed ✓"
}

deploy_agent_host() {
    echo "=== Deploying Agent Host runner contract to ${AGENT_HOST_TARGET} ==="
    ./scripts/preflight-agent-host-runtime.sh "$(pwd)"
    ssh -o ConnectTimeout=$SSH_TIMEOUT "$AGENT_HOST_TARGET" "set -euo pipefail
        cd '$AGENT_HOST_REPO'
        git fetch origin main --prune
        git checkout main
        git pull --ff-only origin main
        ./scripts/preflight-agent-host-runtime.sh '$AGENT_HOST_REPO'
        backup_dir=\"/var/backups/kolibri-agent-host/\$(date -u +%Y%m%dT%H%M%SZ)\"
        install -d \"\$backup_dir\"
        if [[ -f '$AGENT_HOST_LAUNCHER' ]]; then
            cp '$AGENT_HOST_LAUNCHER' \"\$backup_dir/kolibri-agent-host\"
        fi
        rollback() {
            rc=\$?
            if [[ \$rc -ne 0 && -f \"\$backup_dir/kolibri-agent-host\" ]]; then
                cp \"\$backup_dir/kolibri-agent-host\" '$AGENT_HOST_LAUNCHER'
                chmod 0755 '$AGENT_HOST_LAUNCHER'
                systemctl restart '$AGENT_HOST_SERVICE' || true
                echo \"agent_host_rollback_applied:\$backup_dir\" >&2
            fi
            exit \$rc
        }
        trap rollback EXIT
        install -m 0755 ops/agent_host.py '$AGENT_HOST_LAUNCHER'
        KOLIBRI_AGENT_HOST_REQUIRE_LAUNCHER=1 KOLIBRI_AGENT_HOST_LAUNCHER='$AGENT_HOST_LAUNCHER' ./scripts/preflight-agent-host-runtime.sh '$AGENT_HOST_REPO'
        systemctl restart '$AGENT_HOST_SERVICE'
        systemctl is-active --quiet '$AGENT_HOST_SERVICE'
        KOLIBRI_AGENT_HOST_REQUIRE_LAUNCHER=1 KOLIBRI_AGENT_HOST_LAUNCHER='$AGENT_HOST_LAUNCHER' ./scripts/preflight-agent-host-runtime.sh '$AGENT_HOST_REPO'
        trap - EXIT
        echo \"agent_host_backup:\$backup_dir\"
    "
    echo "Agent Host deployed ✓"
}

deploy_network() {
    echo "=== Deploying Kolibri Network to all servers ==="
    for srv in kolibri-main kolibri-uiap kolibri-qjns kolibri-9fts; do
        scp -o ConnectTimeout=$SSH_TIMEOUT infra/network/api.py $srv:/opt/kolibri-network/ 2>/dev/null && \
        ssh -o ConnectTimeout=$SSH_TIMEOUT $srv "systemctl restart kolibri-network" 2>/dev/null && \
        echo "  $srv ✓" || echo "  $srv ✗ (skipped)"
    done
}

case $SERVER in
    main)   deploy_main ;;
    uiap)   deploy_uiap ;;
    qjns)   deploy_qjns ;;
    9fts)   deploy_9fts ;;
    home)   deploy_home ;;
    agent-host) deploy_agent_host ;;
    network) deploy_network ;;
    all)
        deploy_main
        deploy_uiap
        deploy_qjns
        deploy_home
        echo "=== All deployed ==="
        ;;
    *)
        echo "Usage: $0 [main|uiap|qjns|9fts|home|agent-host|network|all]"
        exit 1
        ;;
esac

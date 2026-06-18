#!/bin/bash
# Kolibri AI Platform — Deploy script
# Usage: ./scripts/deploy.sh [main|uiap|qjns|9fts|home|all]

set -e

SERVER=${1:-all}
SSH_TIMEOUT=10

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

deploy_new() {
    echo "=== Deploying Kolibri (Worker) ==="
    scp -o ConnectTimeout=$SSH_TIMEOUT infra/network/api.py kolibri-new:/opt/kolibri-network/
    ssh -o ConnectTimeout=$SSH_TIMEOUT kolibri-new "systemctl restart kolibri-network"
    echo "Kolibri-new deployed ✓"
}

deploy_network() {
    echo "=== Deploying Kolibri Network to all servers ==="
    for srv in kolibri-main kolibri-uiap kolibri-qjns kolibri-9fts kolibri-new; do
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
    new)    deploy_new ;;
    network) deploy_network ;;
    all)
        deploy_main
        deploy_uiap
        deploy_qjns
        deploy_home
        deploy_new
        echo "=== All deployed ==="
        ;;
    *)
        echo "Usage: $0 [main|uiap|qjns|9fts|home|new|network|all]"
        exit 1
        ;;
esac

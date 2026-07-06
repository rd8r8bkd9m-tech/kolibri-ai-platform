#!/usr/bin/env python3
"""Register all 21 servers in the Control Plane."""

import json
import urllib.request
import urllib.error
import sys

CONTROL_PLANE = "http://192.168.88.210:9101"

SERVERS = [
    {"node_id": "home", "hostname": "plastilin", "role": "command_node_gateway", "ip": "10.99.0.1", "capabilities": ["mesh", "redis", "control_plane"]},
    {"node_id": "main", "hostname": "kolibri-main-api", "role": "control_plane", "ip": "10.99.0.2", "capabilities": ["control_plane", "api_gateway", "nginx"]},
    {"node_id": "primary", "hostname": "kolibri", "role": "hybrid", "ip": "10.99.0.10", "capabilities": ["codex", "mimo", "runner:codex", "runner:mimo"]},
    {"node_id": "uiap", "hostname": "kolibri-rag-knowledge", "role": "knowledge_model_node", "ip": "10.99.0.3", "capabilities": ["rag", "knowledge", "chromadb"]},
    {"node_id": "qjns", "hostname": "kolibri-tools-executor", "role": "remote_agent", "ip": "10.99.0.4", "capabilities": ["tools", "executor", "bash"]},
    {"node_id": "9fts", "hostname": "kolibri-inference-recovery", "role": "implementation_model_node", "ip": "10.99.0.5", "capabilities": ["inference", "model", "formulalm"]},
    {"node_id": "new", "hostname": "kolibri-worker-backup", "role": "review_agent", "ip": "10.99.0.6", "capabilities": ["worker", "backup", "review"]},
    {"node_id": "server-kfrm", "hostname": "server-kfrm", "role": "execution", "ip": "10.99.0.31", "capabilities": ["execution", "heavy_tests"]},
    {"node_id": "reserve242", "hostname": "kolibri-qa-security", "role": "reserve", "ip": "10.99.0.21", "capabilities": ["qa", "security"]},
    {"node_id": "highload", "hostname": "kolibri-ci-build-highload", "role": "execution", "ip": "10.99.0.19", "capabilities": ["ci", "build", "highload"]},
    {"node_id": "paris", "hostname": "kolibri-paris-build-reserve", "role": "reserve", "ip": "10.99.0.20", "capabilities": ["reserve", "build"]},
    {"node_id": "agent-01", "hostname": "kolibri-backend-lead", "role": "execution", "ip": "10.99.0.8", "capabilities": ["backend", "python", "fastapi"]},
    {"node_id": "agent-02", "hostname": "kolibri-frontend-design", "role": "execution", "ip": "10.99.0.9", "capabilities": ["frontend", "react", "typescript"]},
    {"node_id": "agent-03", "hostname": "kolibri-infra-network", "role": "execution", "ip": "10.99.0.11", "capabilities": ["infra", "network", "devops"]},
    {"node_id": "agent-04", "hostname": "kolibri-qa-browser", "role": "execution", "ip": "10.99.0.12", "capabilities": ["qa", "browser", "playwright"]},
    {"node_id": "agent-05", "hostname": "kolibri-security-audit", "role": "execution", "ip": "10.99.0.13", "capabilities": ["security", "audit", "scanner"]},
    {"node_id": "agent-06", "hostname": "kolibri-docs-knowledge", "role": "execution", "ip": "10.99.0.14", "capabilities": ["docs", "knowledge", "writing"]},
    {"node_id": "agent-07", "hostname": "kolibri-formulalm-eval", "role": "model", "ip": "10.99.0.15", "capabilities": ["formulalm", "model", "training"]},
    {"node_id": "agent-08", "hostname": "kolibri-rag-eval", "role": "model", "ip": "10.99.0.16", "capabilities": ["rag", "eval", "benchmark"]},
    {"node_id": "agent-09", "hostname": "kolibri-release-canary", "role": "execution", "ip": "10.99.0.17", "capabilities": ["release", "canary", "deploy"]},
    {"node_id": "agent-10", "hostname": "kolibri-hk-edge-load", "role": "execution", "ip": "10.99.0.18", "capabilities": ["edge", "load", "balancing"]},
]

def register_server(server: dict) -> bool:
    url = f"{CONTROL_PLANE}/v1/nodes/register"
    data = json.dumps(server).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        result = json.loads(resp.read().decode())
        print(f"  ✓ {server['node_id']}: {result.get('status', 'ok')}")
        return True
    except Exception as e:
        print(f"  ✗ {server['node_id']}: {e}")
        return False

def main():
    print("Registering 21 servers in Control Plane...")
    success = 0
    for server in SERVERS:
        if register_server(server):
            success += 1
    print(f"\nResult: {success}/{len(SERVERS)} registered")
    return 0 if success == len(SERVERS) else 1

if __name__ == "__main__":
    sys.exit(main())

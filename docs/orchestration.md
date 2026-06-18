# Kolibri AI — Server Orchestration Guide

## Architecture

```
MacBook (Orchestrator)
    │
    ├── scripts/orchestrate.sh — CLI for managing all servers
    │
    ├── home (10.99.0.1)    — Training Hub, Redis
    ├── main (10.99.0.2)    — API Gateway, Frontend, Nginx
    ├── uiap (10.99.0.3)    — RAG Engine, ChromaDB
    ├── qjns (10.99.0.4)    — Agent Executor, MiMo Code
    ├── 9fts (10.99.0.5)    — Inference, llama.cpp
    └── kolibri (10.99.0.6) — Worker, General compute
```

## Quick Start

```bash
# Check all servers
./scripts/orchestrate.sh health

# Run MiMo Code on specific server
./scripts/orchestrate.sh run uiap "Optimize ChromaDB index for construction documents"

# Run task in parallel across all servers
./scripts/orchestrate.sh parallel "Review code quality and suggest improvements"

# Deploy to specific server
./scripts/orchestrate.sh deploy main

# Deploy to all servers
./scripts/orchestrate.sh deploy all

# View server status
./scripts/orchestrate.sh status main

# View server logs
./scripts/orchestrate.sh logs main 100

# Execute arbitrary command
./scripts/orchestrate.sh exec uiap "systemctl status chromadb"
```

## Server Roles

| Server | Role | MiMo Code Tasks |
|--------|------|-----------------|
| **home** | Training Hub | Model training, data generation, fine-tuning |
| **main** | API Gateway | Frontend builds, API routing, nginx config |
| **uiap** | RAG Engine | ChromaDB optimization, embeddings, knowledge base |
| **qjns** | Agent Executor | Code execution, tool calling, planning |
| **9fts** | Inference | Model inference, llama.cpp, GGUF conversion |
| **kolibri** | Worker | General compute, backup, maintenance |

## Parallel Development Workflow

1. **Assign modules to servers** based on their role
2. **Run tasks in parallel** using `orchestrate.sh parallel`
3. **Collect results** from logs
4. **Deploy changes** to specific servers

### Example: Feature Development

```bash
# 1. Backend changes on main
./scripts/orchestrate.sh run main "Add user authentication to /api/chat endpoint"

# 2. RAG improvements on uiap
./scripts/orchestrate.sh run uiap "Implement hybrid search with BM25 reranking"

# 3. Agent tools on qjns
./scripts/orchestrate.sh run qjns "Create file operations tool for agent"

# 4. Deploy all changes
./scripts/orchestrate.sh deploy all
```

## Automated Backups

```bash
# Install backup timer on main server
./scripts/orchestrate.sh exec main "cp /opt/kolibri-ai/scripts/kolibri-backup.service /etc/systemd/system/"
./scripts/orchestrate.sh exec main "cp /opt/kolibri-ai/scripts/kolibri-backup.timer /etc/systemd/system/"
./scripts/orchestrate.sh exec main "systemctl enable --now kolibri-backup.timer"
```

## SSH Setup

Ensure SSH keys are configured for each server:

```bash
# Generate key if needed
ssh-keygen -t ed25519

# Copy to each server
ssh-copy-id kolibri-home
ssh-copy-id kolibri-main
ssh-copy-id kolibri-uiap
ssh-copy-id kolibri-qjns
ssh-copy-id kolibri-9fts
ssh-copy-id kolibri-new
```

## Monitoring

```bash
# Check Prometheus metrics
curl http://localhost:9090/targets

# Check Grafana dashboards
open http://localhost:3000
```

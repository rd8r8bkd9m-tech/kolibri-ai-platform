# Kolibri AI — Server Orchestration Guide

This document describes two different modes:

- **Operational mode**: the original 6-node service guide for deployed Kolibri
  components.
- **FormulaLM experiment mode**: the 19-server `estimate-pilot-001` research
  orchestration. It is gated by `AGENTS.md`,
  `ops/experiments/estimate-pilot-001/role_map.json`, and the FormulaLM schemas
  under `ops/formulalm/`.

Do not treat FormulaLM experiment roles as deploy permission. MiMo and remote
Codex workers are bounded executors; Codex remains reviewer and release
manager.

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

## FormulaLM Experiment Mode

The FormulaLM pilot uses all 19 server keys from `ops/agents.yml`, not only the
6 operational VPN nodes above. The canonical run ID is `estimate-pilot-001`, and
the canonical run directory is:

```text
/srv/kolibri/runs/estimate-pilot-001/
```

Before task fanout, run:

```bash
python3 scripts/validate_formulalm_experiment.py --dry-run
```

The validator proves that:

- `ops/experiments/estimate-pilot-001/role_map.json` covers every server in
  `ops/agents.yml` exactly once;
- the role map has eight FormulaLM islands with unique seeds;
- FormulaLM worker schemas are valid JSON;
- the sample task envelope targets the 401-421 estimate pilot and keeps source
  data immutable;
- safety text forbids unsafe permissions, broad process kills, source-data
  mutation, final-test leakage, secret logging, and success claims without
  metrics;
- 19 task envelopes can be generated in dry-run mode without contacting servers
  or starting training.

FormulaLM scaling order:

1. hardening and local validation;
2. read-only preflight;
3. read-only fanout to healthy servers;
4. one controlled mutation in an isolated worktree;
5. 24/7 queue only after Codex reviews diffs, checks, metrics, and risks.

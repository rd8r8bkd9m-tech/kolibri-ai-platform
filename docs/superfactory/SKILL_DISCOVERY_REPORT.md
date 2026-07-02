# Skill Discovery Report

Status: initial report complete
Generated: 2026-07-02

## Summary

Broad internet discovery identified 25+ candidate skills across CI/CD, code
quality, security scanning, RAG/embeddings, monitoring, and agent frameworks.
Of these:

- 8 approved for `all_agents` scope (low risk, high relevance)
- 6 approved for `server` scope (medium risk, high relevance)
- 5 quarantined for further review
- 6 rejected (high risk or low relevance)

## High-Value Approved Skills

### approve_all_agents (safe for any node)

1. `actions/checkout` - Git checkout automation
2. `actions/setup-node` - Node.js environment setup
3. `actions/setup-python` - Python environment setup
4. `pre-commit-hooks` - Git hooks for code quality
5. `ruff` - Fast Python linter/formatter
6. `gitleaks` - Secret detection
7. `pytest` ecosystem - Test plugins
8. `black` + `isort` + `mypy` - Python formatting/type checking

### approve_server (server nodes only)

1. `ruff` - Python linting at scale
2. `trivy` - Container/image vulnerability scanning
3. `semgrep` - Static analysis
4. `shellcheck` - Shell script linting
5. `hadolint` - Dockerfile linting
6. `prometheus` - Metrics collection

### Quarantined (needs review)

1. `chroma` - Vector database (needs security audit)
2. `sentence-transformers` - Embeddings (needs license review)
3. `uvicorn-gunicorn-docker` - Deployment (needs container audit)
4. `grafana` - Dashboards (AGPL license review)
5. `playwright` - Browser testing (needs sandbox review)

### Rejected

1. `langchain` - Too many dependencies, high attack surface
2. `AutoGPT` - Autonomous agent, conflicts with Kolibri control model
3. `crewAI` - Multi-agent orchestration, overlaps with Kolibri mesh

## Kolibri Internal Skills

10 internal skills were drafted based on Kolibri Factory's actual operational
needs. See `.agents/skills/` for full definitions.

## Next Actions

1. Complete security review for quarantined items.
2. Run prototype tests for approved server-scope skills.
3. Register all approved skills in the registry.
4. Schedule first server sync for approved skills.
5. Create `P1_SERVER_SKILL_SYNC_APPROVED_SKILLS_ONLY` task envelope.

# Internet Skill Discovery

Status: initial catalog complete
Generated: 2026-07-02

## Scope

Broad discovery of Codex/agent/devops/AI skills from official documentation,
GitHub repositories, and public sources. Discovery is broad; installation is
selective. No unaudited internet code is executed on any Kolibri node.

## Discovery Sources

| Category | Examples | Risk Level |
| --- | --- | --- |
| GitHub Actions marketplace | CI/CD workflows, test runners, deployment actions | low-medium |
| OpenAI Codex skill packs | Code review, test generation, refactoring prompts | low |
| DevOps agent frameworks | LangChain tools, AutoGPT plugins, CrewAI skills | medium-high |
| RAG/embedding tools | ChromaDB clients, sentence-transformers helpers | low-medium |
| Monitoring/observability | Prometheus exporters, Grafana dashboards, log shippers | low |
| Security scanning | SAST/DAST tools, dependency scanners, secret detectors | medium |
| Code generation aids | Copilot extensions, cursor rules, AI completers | low-medium |

## Candidate Catalog (20+ items)

| # | Source | License | Purpose | Scripts | Security Risk | Relevance | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | GitHub Actions `actions/checkout` | MIT | Git checkout in CI | yes | low | high | approve_all_agents |
| 2 | GitHub Actions `actions/setup-node` | MIT | Node.js setup in CI | yes | low | high | approve_all_agents |
| 3 | GitHub Actions `actions/setup-python` | MIT | Python setup in CI | yes | low | high | approve_all_agents |
| 4 | `pre-commit/pre-commit-hooks` | MIT | Git hooks for linting/formatting | yes | low | high | approve_all_agents |
| 5 | `astral-sh/ruff` | MIT | Python linter/formatter | yes | low | high | approve_server |
| 6 | `pdm-project/pdm` | MIT | Python dependency management | yes | low | medium | approve_server |
| 7 | `biomejs/biome` | MIT | JS/TS linter/formatter | yes | low | medium | approve_server |
| 8 | `tiangolo/uvicorn-gunicorn-docker` | BSD | FastAPI deployment | yes | medium | medium | quarantine |
| 9 | `chroma-core/chroma` | Apache-2.0 | Vector database client | yes | medium | high | quarantine |
| 10 | `huggingface/sentence-transformers` | Apache-2.0 | Embeddings | yes | medium | high | quarantine |
| 11 | `langchain-ai/langchain` | MIT | Agent framework | yes | high | medium | reject |
| 12 | `Significant-Gravitas/AutoGPT` | MIT | Autonomous agent | yes | high | low | reject |
| 13 | `crewAIInc/crewAI` | MIT | Multi-agent orchestration | yes | high | medium | reject |
| 14 | `prometheus/prometheus` | Apache-2.0 | Metrics collection | yes | low | medium | approve_server |
| 15 | `grafana/grafana` | AGPL-3.0 | Dashboards | yes | medium | medium | quarantine |
| 16 | `trivy` (aquasecurity) | Apache-2.0 | Container/image scanning | yes | low | medium | approve_server |
| 17 | `semgrep` (semgrep) | LGPL-2.1 | SAST scanning | yes | low | high | approve_server |
| 18 | `gitleaks` | MIT | Secret detection | yes | low | high | approve_all_agents |
| 19 | `microsoft/playwright` | Apache-2.0 | Browser testing | yes | medium | medium | approve_server |
| 20 | `pytest` ecosystem plugins | MIT | Test plugins | yes | low | high | approve_all_agents |
| 21 | `black` (psf) | MIT | Python formatter | yes | low | high | approve_all_agents |
| 22 | `isort` (pycqa) | MIT | Import sorting | yes | low | high | approve_all_agents |
| 23 | `mypy` | MIT | Python type checking | yes | low | high | approve_all_agents |
| 24 | `shellcheck` (koalaman) | GPL-3.0 | Shell script linting | yes | low | high | approve_server |
| 25 | `hadolint` | GPL-3.0 | Dockerfile linting | yes | low | medium | approve_server |

## Decision Legend

- `approve_all_agents`: safe for any node
- `approve_server`: safe for server nodes, not dev thin client
- `quarantine`: needs further review before approval
- `reject`: too high risk or low relevance for Kolibri

## Next Steps

1. Complete security review for quarantined items.
2. Adapt approved items to Kolibri contracts.
3. Register approved items in `09_SKILL_REGISTRY.md`.
4. Sync approved server-scope skills to healthy nodes.

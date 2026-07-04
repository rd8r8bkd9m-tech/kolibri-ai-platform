# Current Project Truth

Timestamp: `2026-07-04TUTC`

Repository:

- Working repo: `/srv/kolibri-ai-platform`.
- Branch: `p0/governing-chat-mcp-action-start-factory-20260704`.
- Base head: `3ce233f9c3a29a425f7d6d63a368dde14f8522a9`.
- Dirty runtime checkout `/srv/kolibri/kolibri-ai-platform` was not used.

Fleet/runtime facts from this run:

- Control Plane `10.99.0.2:9101`: timeout / HTTP `000`.
- Local `127.0.0.1:9101`: refused connection.
- Local `kolibri-kfm-mimocode.service`: active.
- Local `kolibri-agent-host.service`: activating.
- Local `kolibri-factory-control.service`: inactive.
- Local `kolibri-telegram-gateway.service`: inactive.

GitHub:

- Repo: `rd8r8bkd9m-tech/kolibri-ai-platform`.
- Related PR #162 changes Factory source-of-truth, registry, queue diagnostics and backend status parsing.

FormulaLM:

- Repro suite: `/srv/kolibri/formulalm-tests`.
- Baseline report: `/srv/kolibri/formulalm-tests/reports/formulalm_repro_eval_v1.json`.
- Baseline: aggregate `0.066391`, exact `0/10`, contains `0/10`.

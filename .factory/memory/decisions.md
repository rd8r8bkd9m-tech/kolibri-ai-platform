# Factory Decisions

## 2026-06-20: Bootstrap Factory Before Fanout

Decision: create Factory v1 scaffolding, schemas, policies, dry-run scripts, and
two canary tasks before restarting broad MiMo fanout.

Reason: previous remote agent attempts produced timeouts and ambiguous results;
the user needs a persistent, reviewable, parallel development factory rather
than sequential firefighting.

Assumption: existing dirty changes in `backend/public_proxy.py`,
`frontend/src/hooks/useCluster.js`, `scripts/agent_factory.py`,
`docs/agent-factory.md`, and `infra/systemd/kolibri-agent-factory.service` are
kept and treated as current work, not reverted.

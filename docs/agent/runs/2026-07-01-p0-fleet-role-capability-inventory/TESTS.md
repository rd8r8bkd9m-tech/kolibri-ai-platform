# Tests

Task: `P0_FLEET_ROLE_CAPABILITY_INVENTORY_2026_07_01`

Checks from the server inventory and relay:

- Control Plane health was read-only queried and returned `ok`.
- Node inventory covered 42 visible Control Plane node cards.
- Generated inventory separated owner-facing server nodes, mesh shadow cards,
  and stale metadata cards.
- Generated target pools include implementation, review, QA, RAG/knowledge,
  Telegram, observability, canary deploy, and model/LLM buckets.
- Generated repair backlog includes qjns credentials, main runner auth,
  stale mesh/metadata cards, home/home-live freshness, and queue retention.

Canonical alias checks:

```bash
test -f docs/agent/runs/2026-07-01-p0-fleet-role-capability-inventory/RESULT.md
test -f docs/agent/runs/2026-07-01-p0-fleet-role-capability-inventory/NEXT.md
test -f docs/agent/intelligence/2026-07-01-fleet-role-capability-inventory/FLEET_ROLE_MATRIX.md
test -f docs/agent/intelligence/2026-07-01-fleet-role-capability-inventory/NODE_BLOCKERS.md
test -f docs/agent/intelligence/2026-07-01-fleet-role-capability-inventory/TARGET_POOLS.md
test -f docs/agent/intelligence/2026-07-01-fleet-role-capability-inventory/NEXT_REPAIR_TASKS.md
git diff --check
```

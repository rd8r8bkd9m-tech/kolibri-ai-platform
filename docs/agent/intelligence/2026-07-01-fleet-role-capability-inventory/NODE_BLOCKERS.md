# Node Blockers

Task: `P0_FLEET_ROLE_CAPABILITY_INVENTORY_2026_07_01`

This file extracts the blocker view from the fleet inventory. The full role
matrix is in `FLEET_ROLE_MATRIX.md`, safe pools are in `TARGET_POOLS.md`, and
repair sequencing is in `NEXT_REPAIR_TASKS.md`.

## Blockers

1. `qjns` is online and disk pressure is resolved, but GitHub/MIMO access is
   not usable for review or implementation work. Current classification:
   `missing_node_github_credential` and `provider_access_denied`.
2. `main` is online and advertises runner capabilities, but previous runner
   auth checks showed auth risk and it has low available memory. Use only for
   bounded probes until auth smoke passes.
3. `home` and `home-live` have owner-facing capabilities, but the latest
   inventory classified their cards as stale/non-fresh. Do not target them for
   new owner-facing or Telegram work until heartbeat freshness is repaired.
4. `primary-candidate` remains the practical command/review node, but the
   inventory also flagged freshness ambiguity. Use it for controlled tasks and
   keep exact task endpoint checks as the source of truth.
5. Stale mesh shadow cards such as `mesh-agent-04..09`, `mesh-home`,
   `mesh-main`, `mesh-primary`, `mesh-qjns`, and similar cards must not be used
   for implementation, review, deploy, or canary tasks until refreshed.
6. Metadata-only cards such as `agent-01..09`, `9fts`, `highload`, `paris`,
   `reserve242`, `server-kfrm`, and `smoke-primary` need a retention/TTL
   policy before the scheduler treats them as reliable capacity.
7. The Control Plane queue is large and truncated in aggregate views. Exact
   task endpoints remain authoritative; a separate queue audit is required
   before broad scheduling.

## Safe Handling

- Prefer fresh online cards with explicit `runner:*` capabilities for code
  changes.
- Use `uiap` for RAG/knowledge work, not general implementation.
- Use qjns only for read-only or credential-repair probes until GitHub/MIMO
  blockers are cleared.
- Do not repair or mutate infrastructure from inventory tasks.

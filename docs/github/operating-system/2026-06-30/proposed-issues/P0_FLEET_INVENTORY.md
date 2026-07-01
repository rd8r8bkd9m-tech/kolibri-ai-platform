# P0 Fleet Resource Inventory and Reachability

## Context

The owner-facing server set has 20 servers, while Control Plane exposes more node cards including stale/mesh metadata cards.

## Scope

- Server inventory.
- Node cards.
- Roles/capabilities.
- Disk/memory/CPU.
- API/SSH emergency reachability.

## Acceptance

- Every node has status, role, route, blocker and next action.
- Problem nodes are not used blindly.

## Forbidden

- No destructive cleanup.
- No secret printing.

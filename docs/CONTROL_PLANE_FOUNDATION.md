# Control Plane Foundation

This branch currently implements the control plane as Fabric/Superfactory Python services.

## Existing Foundation

- `ops/factory_control.py`: task envelopes, Redis state, node state, Fabric routes, Mini App task creation, Superfactory status.
- `ops/agent_host.py`: agent execution contract.
- `ops/telegram_superfactory.py`: Telegram auth, receiver mode, runner policy, runner selection.
- `docs/fabric-api-first-control.md`: API-first doctrine.

## V1 Foundation Rules

- Preserve `/v1/fabric/*` compatibility until a migration map and tests exist.
- Normalize agent/task/event/artifact/approval vocabulary across Python and Rust foundation.
- Keep dangerous commands behind policy and explicit approval.
- Treat Redis state as current runtime state, not permanent source of truth for future V1.

## Next Implementation Step

Add a compatibility map and tests before changing endpoint shapes.

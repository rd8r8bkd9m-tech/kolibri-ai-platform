# Regression Test Plan

Required tests:

- Registry validates cleanly.
- Alias matching maps canonical physical nodes safely.
- `mesh-agent-*` never maps to physical `agent-*`.
- `allowed_nodes` fallback works only when explicit.
- Capability aliases work only through registry.
- Runner capability is required when a runner is requested.
- Blocked diagnostics include actionable reason.
- Bounded task listing does not remove legacy full listing behavior.
- Port registry preserves shared port services.

Implemented targeted tests cover these areas.


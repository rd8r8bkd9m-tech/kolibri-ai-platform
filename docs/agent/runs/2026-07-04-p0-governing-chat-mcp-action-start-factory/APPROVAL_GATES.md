# Approval Gates

Allowed without extra owner approval:

- A1 read-only inspection.
- A2 bounded docs/test task submission when Control Plane is healthy.

Requires owner approval:

- A3 canary deploy/restart with rollback.
- Service restart.
- Firewall/network changes.
- GitHub merge or ready-for-review state changes.
- Node bootstrap or credential rotation.

Disabled:

- A4 broad autonomous rollout.
- A5 destructive or irreversible operations.

# MIMO Auto Development Policy

Date: 2026-07-02
Status: active routing preference.

## Rule

For development work on non-control servers, prefer MIMO Auto.

Use Codex primarily for:

- director/orchestrator decisions;
- code review and release gates;
- incident triage;
- tasks where MIMO is unavailable, unauthenticated, or policy-blocked.

## Task Envelope Convention

Development envelopes should include:

```json
{
  "runner": "mimo",
  "mimo_mode": "auto",
  "permission_pack": "factory_auto_permit",
  "approval_mode": "auto_within_factory_rules",
  "required_capability": "generic_implementation"
}
```

Control Plane and Agent Host may still execute through the current MIMO runner
contract, but the owner-facing policy is MIMO Auto for server development.

For KFM and other trusted factory nodes, `factory_auto_permit` means no manual
owner confirmation for normal non-destructive work: repository inspection,
factory namespace search, task-scope writes, artifact creation, repair task
creation and fallback routing. It does not permit raw secret disclosure,
private-key copying, provider billing, destructive actions, receiver migration,
force-push or direct push to `main`.

## Fallback

If a node lacks `runner:mimo`, has stale heartbeat, or fails MIMO auth, the
factory must create or reference a repair task and route to the next fresh
MIMO-capable server.

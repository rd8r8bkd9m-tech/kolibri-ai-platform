# Result

- Fixed the Home lease capability contract bug in the control-plane runner path.
- `compatible()` now evaluates required and runner capabilities against an effective set composed from the lease request capabilities plus the persisted node capabilities.
- This prevents an eligible registered Home/Home NOC node from receiving an empty-lease 204 solely because the lease request omitted capabilities.
- Existing runner blocking behavior remains enforced.
- Focused tests pass.
- Kiosk deploy was intentionally not rerun.

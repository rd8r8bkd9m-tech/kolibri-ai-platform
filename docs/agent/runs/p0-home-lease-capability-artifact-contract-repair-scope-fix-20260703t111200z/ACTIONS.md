# Actions

- Created this run artifact set at the required exact path before finalizing.
- Reused the previous blocked-at-finalization diagnosis: the repair needed `tests/test_factory_runtime.py` in scope, and kiosk/Home NOC deploy must not be retried until the lease/runner behavior is proven.
- Updated `ops/factory_control.py` so lease compatibility uses the effective capability set from both the current lease request and the persisted node record.
- Added a focused regression in `tests/test_factory_runtime.py` for a `home-live` owner task whose lease request omits capabilities while the registered node record has `generic_implementation` and `runner:codex`.
- Preserved runner safety: a node with the registered runner capability but blocked runner status is still rejected.
- Did not perform local Mac work, provider lifecycle changes, secret handling, main push, force push, or kiosk deploy.

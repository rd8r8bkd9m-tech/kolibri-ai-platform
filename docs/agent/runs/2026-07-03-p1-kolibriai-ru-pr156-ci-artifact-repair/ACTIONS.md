# Actions

## CI Failure

- Inspected GitHub Actions run `28654923623`.
- Failing job: `ci`.
- Failing step: `Pytest tests`.
- Failing test: `tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint`.

## Repair

- Restored an explicit frontend factory status surface that references `/api/factory/status`.
- Kept startup behavior unchanged: the factory status endpoint is only called from a user-triggered refresh button.
- Added the required visible labels for the status contract:
  - `Фабрика Колибри`
  - `Свежие`
  - `Деградируют`
  - `Устарели`
- Added canonical run artifacts under this directory.

## Guardrails Observed

- Did not deploy or restart services.
- Did not merge or force push.
- Did not mutate credentials.
- Did not touch Telegram, billing, FormulaLM, Control Plane, or model gateway work.

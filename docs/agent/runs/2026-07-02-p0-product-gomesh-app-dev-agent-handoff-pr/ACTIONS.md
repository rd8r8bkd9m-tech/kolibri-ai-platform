# Actions

- Added `GOMESH_OWNER_RULES`, required artifacts and default verification
  commands in `ops/factory_control.py`.
- Added `gomesh_dev_handoff_envelope()` to create a concrete owner remote task
  for the active GoMesh Codex agent.
- Added `POST /v1/gomesh/dev/handoff` to create that task through Factory
  Control.
- Added the GoMesh handoff policy to `/v1/fabric/policy`.
- Added focused tests in `tests/test_factory_control_gomesh_handoff.py`.
- Updated the Fabric API surface test for the new endpoint.


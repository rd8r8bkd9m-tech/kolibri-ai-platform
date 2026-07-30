# Local public AG-UI estimate journey

Captured: 2026-07-30  
Release task: R1-008, public estimate creation

## Result

`PROVEN` on the canonical local V3 public HTTP boundary.

The test starts from an empty temporary database and uses the native bearer
transport. It does not insert a project, thread, message, document or estimate
record directly.

The journey proves:

1. a registered and entitled customer posts a construction-estimate request
   to `POST /v1/chat/ag-ui`;
2. Product Chat automatically creates the canonical thread and project;
3. the AG-UI stream contains the real `estimate_engine_calculate` tool call
   followed by an `EstimateEditor` presentation;
4. the estimate is persisted as version 1 and is available from the public
   project estimate API;
5. durable history contains the user request and typed tool result;
6. document listing projects the same project;
7. `estimate_versions.origin_run_id` equals the accepted internal Product Chat
   run ID;
8. a second tenant receives 404 and a user without the construction
   entitlement receives 403.

The provider boundary is deterministic in this test; it exercises the same
runtime registry and structured-output contract without relying on network
availability.

## Verification

```text
backend/venv/bin/python -m pytest -q \
  backend/tests/test_public_estimate_journey.py \
  backend/tests/test_estimate_engine_api.py \
  backend/tests/test_estimate_artifact.py \
  backend/tests/test_runtime_skills.py

15 passed
```

An independent rerun of the exact journey test also passed:

```text
1 passed
```

Production was not contacted or changed. The immutable-candidate browser
replay and physical-device acceptance remain later release gates.

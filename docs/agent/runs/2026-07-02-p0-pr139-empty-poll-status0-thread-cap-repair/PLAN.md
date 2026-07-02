# PLAN

Task: repair PR #139 high-stage empty lease poll `status 0` while preserving the fixed HTTP worker thread cap.

Plan:

1. Continue from PR #139 head `9ffc05d1d3c00fe81d213b63fe2acdca3ad72dc8`.
2. Keep the hard HTTP worker ceiling at `64`.
3. Remove blocking admission from the accept loop so high-stage clients are accepted and queued by the fixed executor instead of timing out before accept.
4. Keep `/v1/tasks/lease` empty-poll behavior as `200 no_task`.
5. Add regression coverage that forbids restoring `_request_slots.acquire()` in `process_request`.
6. Run focused factory capacity/runtime tests.
7. Open a stacked PR and run the production runtime canary only after CI is green.

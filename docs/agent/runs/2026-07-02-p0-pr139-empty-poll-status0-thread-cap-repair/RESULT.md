# RESULT

Implemented a focused repair for the PR #139 runtime regression.

Root cause addressed:

- PR #139 fixed HTTP worker thread growth but added blocking semaphore admission in `FactoryThreadingHTTPServer.process_request`.
- Under stages `250/500/1000`, the accept loop could block waiting for a worker slot, leaving some empty-poll clients to time out before the server accepted the connection. The canary then recorded empty-poll `status 0` while thread count stayed capped.

Implemented result:

- The server still uses a capped `ThreadPoolExecutor` with `max_workers <= 64`.
- Accepted sockets are submitted directly to the fixed executor.
- No extra worker threads are created beyond the executor cap.
- No `503` or `overloaded` lease path is introduced.
- Empty queue lease polls remain `200 no_task`.

Decision:

- Code is ready for CI and controlled runtime canary.
- Merge is not approved until the strict live canary passes all six stages with zero lease/empty `status 0` and zero `5xx`.

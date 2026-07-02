# STATUS0 WITH THREAD CAP CAUSE

Observed from PR #139 live canary:

- Thread growth was repaired: high-stage runtime stayed around the fixed worker cap.
- Empty-poll `status 0` returned at stages `250`, `500`, and `1000`.
- Lease equality still held for created tasks.

Likely cause:

- Semaphore admission blocked inside `FactoryThreadingHTTPServer.process_request` before submitting work to the executor.
- When all worker slots were busy, the accept loop could stop accepting new sockets until a slot freed.
- High-stage empty poll clients timed out at the transport layer and were counted as `status 0`.

Repair:

- Remove blocking semaphore admission from `process_request`.
- Let the fixed `ThreadPoolExecutor` queue accepted sockets.
- Preserve the hard worker cap through the executor's `max_workers <= 64`.

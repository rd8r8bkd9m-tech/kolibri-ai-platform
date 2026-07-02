# RESULT

Status: useful remote implementation completed; wrapper originally failed only because exact run artifacts were missing.

The repair addresses PR #137's canary failure mode:

- PR #137 canary had no `status0` through stage 100.
- Stage 100 failed because `threads=122`, above the canary gate `threads <= 90`.

This patch clamps worker threads and adds admission backpressure:

- `HTTP_WORKER_THREAD_CEILING = 64`
- `HTTP_MAX_WORKERS_CONFIGURED` records the environment value.
- `HTTP_MAX_WORKERS` is clamped to `1..64` even if runtime env says `256`.
- `FactoryThreadingHTTPServer` exposes `max_workers` and uses a `BoundedSemaphore` around executor submission.
- Extra accepted requests wait for a worker slot. They are not converted into 503/overload responses.

Expected next gate: GitHub CI, then controlled runtime canary with backup/rollback.

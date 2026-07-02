# THREAD_GROWTH_CAUSE

Observed cause:

- PR #137 introduced a fixed HTTP executor but left the runtime-configurable worker count at `FACTORY_HTTP_MAX_WORKERS`, defaulting to `256`.
- The live runtime canary saw healthy HTTP statuses but stage 100 produced `122` process threads.
- The canary gate fails when `after.threads > 90`.

Repair:

- Clamp configured worker count to a hard ceiling of `64`.
- Keep the socket backlog large so bursty empty polls queue at the OS/server boundary.
- Use semaphore-backed admission around the executor so the server applies backpressure without creating a 503/overload lease path.

Synthetic evidence:

- With `FACTORY_HTTP_MAX_WORKERS=256` deliberately set, the subprocess probe reported `max_workers=64`.
- Stages `20/50/100/250/500/1000` all returned `200/no_task`.
- Threads plateaued at `65` through stages `500` and `1000`.

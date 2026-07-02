# ACTIONS

- Continued from PR #139 head `9ffc05d1d3c00fe81d213b63fe2acdca3ad72dc8`.
- Kept `FactoryThreadingHTTPServer` on a capped `ThreadPoolExecutor`.
- Removed semaphore-backed blocking admission from `process_request`.
- Submitted accepted sockets directly to the fixed executor.
- Preserved the no-task lease response contract: empty queue polls return `200 no_task`.
- Did not add a `503`, `overloaded`, or lease rejection path.
- Did not deploy runtime in this commit.

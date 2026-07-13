# V2.1 clean foundation

## Authority

`home` is the only logical Control Plane identity. Provider fallback never changes authority. Legacy names, hardcoded IPs and legacy `/api` routes are not runtime fallbacks.

## Product shape

The shell is a Morphing Conversation:

1. one active project;
2. one continuous conversation;
3. contextual tools only;
4. inline result first;
5. full surface on mobile;
6. no permanent vertical menu;
7. one bird per surface.

## Local data plane

The development foundation uses SQLite and a content-addressed filesystem so the contracts can be exercised locally. The production gate replaces them with PostgreSQL, JetStream and replicated S3-compatible CAS without changing public contracts.

## Completion truth

A task is complete only with a non-empty result, attempt/fence binding, non-empty required artifacts, SHA-256 and independent verifier binding. Heartbeat is not proof of execution.

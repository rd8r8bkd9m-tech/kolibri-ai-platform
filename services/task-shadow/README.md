# Kolibri task shadow

This binary is the first executable Rust parity slice for the Home-first
factory. Python remains the only production task authority. The Rust service
has no adapter capable of mutating Python/Redis task state, binds only to a
loopback address and labels every record `shadow_parity` / `authoritative=false`.

The local shadow listener implements the Python-compatible slice:

- `POST/GET /v1/tasks` and `GET /v1/tasks/{task_id}`;
- `POST /v1/tasks/lease`;
- fenced `heartbeat`, `complete` and `fail` mutations;
- `GET /v1/tasks/{task_id}/events`;
- `POST /v1/tasks/reap-expired`;
- `GET /v1/runtime/summary` with measured task/attempt/lease/event counts.

Task creation and mutation idempotency, total attempt budgets, monotonically
increasing numeric fencing tokens, lease expiry, stale completion rejection,
content-bound result hashes and the independent completion verifier execute in
Rust. A private atomic state snapshot makes local restart replayable; this is
not a production storage or cutover claim.

The durable event, V1 wire and swarm scheduler foundation was imported from
the reviewed donor commit
`69f3b844f2064da0a7d8f5dc3feaa8f90dbca369`. Unrelated donor services were
not imported.

The shared fixture proves:

- `max_attempts` is a total attempt budget;
- heartbeat renewal and lease expiry;
- monotonically increasing numeric fencing tokens;
- rejection of a completion from an expired attempt;
- content-bound result and attempt-binding SHA-256 values;
- an independent `control-plane/home` verifier verdict;
- deterministic replay and Python/Rust summary parity.

Run the Rust replay directly:

```bash
cargo run -p kolibri-task-shadow -- replay contracts/kolibri-os-v1/fixtures/task-lifecycle-parity.json --assert-expected --pretty
```

Run the cross-language check:

```bash
./scripts/check-rust-shadow-parity.sh
```

Run the loopback-only shadow API with an explicit state file:

```bash
cargo run -p kolibri-task-shadow -- serve \
  --bind 127.0.0.1:9191 \
  --state /tmp/kolibri-task-shadow/state.json
```

Every mutating endpoint accepts `Idempotency-Key`; the JSON body spelling
`idempotency_key` remains compatible with Python workers. Sending both with
different values is rejected with HTTP 422.

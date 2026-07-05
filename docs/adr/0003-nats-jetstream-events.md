# ADR-0003: NATS JetStream для event stream

- Решение: все доменные события идут в NATS JetStream.
- Причина: устойчивость к replay, backpressure и удобный fan-out.


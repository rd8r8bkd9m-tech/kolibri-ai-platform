# Руководство разработчика

## Быстрый старт

```bash
# Rust
cargo check --workspace
cargo test --workspace

# Local daemon
cargo run -p kolibri-locald -- --help
```

## Требования

- Rust stable
- PostgreSQL и NATS для полной интеграции (control-plane-итерация)
- Ubuntu machine для kiosk и systemd

## Политика веток

- Не пушить напрямую в `main` в релизный процесс.
- PR через контрольный поток и проверку контрактов.


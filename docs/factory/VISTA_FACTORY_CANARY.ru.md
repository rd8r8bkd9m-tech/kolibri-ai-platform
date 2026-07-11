# Vista Factory Canary

Canary — это обязательная проверка, после которой можно говорить, что фабрика исполняет задачи не только локально.

## Минимальный стенд

```text
server-01: Vista Control Server
server-02: Vista Node Agent
server-03: Vista Node Agent
```

## Проверяемый flow

```text
1. Control Server принимает task.
2. Worker node регистрируется через join-token.
3. Worker шлёт heartbeat.
4. Worker получает lease.
5. Worker создаёт RESULT.md.
6. Worker отправляет artifact.
7. Verifier проверяет required artifacts.
8. Task становится completed.
9. UI видит completed state и artifact.
```

## Команда

```bash
./scripts/run-factory-canary.sh --control-url http://CONTROL_SERVER:8000
```

Canary пишет отчёт:

```text
var/canary/FACTORY_CANARY_REPORT.md
```

## Условия успеха

- `task.completed` есть у каждой canary task;
- `artifact.written` есть;
- `verifier.checked` = passed;
- artifact содержит sha256;
- `fleet/health` видит worker nodes;
- нет fake success без backend.

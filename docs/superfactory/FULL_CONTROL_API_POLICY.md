# Full-Control API Policy

## Принцип

Владелец имеет право отдавать full-control команды через API, но это не право разрушать, спамить, обходить правила, печатать секреты или выполнять необратимые действия без следа.

Full-control означает полную ответственность внутри закона фабрики:

- authenticated;
- authorized;
- traceable;
- signed or token-bound;
- logged;
- scoped by task_id;
- reversible when possible;
- protected from secret leakage.

## Роли

| Role | Назначение |
| --- | --- |
| `owner_root` | Владелец, final authority, может запрашивать full-control действия. |
| `command_node` | Доверенный интерфейс управления: Mac, Home, Telegram, phone, main, primary-candidate. |
| `control_plane` | Нервная система фабрики: очередь, leases, node cards, artifacts. |
| `agent_host` | Исполнитель задач на конкретном узле. |
| `remote_agent` | Codex/MIMO/API агент, выполняющий scoped task. |
| `model_node` | Узел с локальными LLM, embeddings, image/video/model services. |
| `review_agent` | Проверка PR, diff, security, correctness. |
| `qa_agent` | Тесты, браузерные проверки, CI-like validation. |
| `observer` | Read-only мониторинг и отчеты. |

## Политика прав

`owner_root` может запрашивать full-control действия. Все остальные роли получают только ограниченные scoped permissions.

Ни один endpoint не должен принимать вечный общий ключ как единственный механизм доступа. Должен существовать trust plane:

- per-node identity;
- mTLS или signed service tokens;
- WireGuard/mesh VPN как транспорт, если полезно;
- short-lived owner/admin tokens;
- rotating node tokens;
- emergency break-glass token;
- API key/cert rotation policy;
- no secrets in logs;
- no hardcoded credentials.

## Privileged endpoints

Следующие endpoint-ы считаются privileged:

```text
POST /v1/admin/exec
POST /v1/admin/service
POST /v1/admin/git
POST /v1/admin/bootstrap-node
POST /v1/admin/rotate-keys
```

Они требуют:

- role `owner_root` или явно делегированную scoped роль;
- `task_id`, `trace_id`, `source`, `command_node`, `target_node`;
- список разрешенных `write_scope`;
- constraints, которые запрещают destructive действия по умолчанию;
- audit log до и после выполнения;
- redaction всех секретов в stdout/stderr/artifacts.

## Запрещено по умолчанию

- destructive git commands без отдельного owner approval;
- push to main;
- force push;
- git clean/reset без отдельного owner approval;
- печать секретов, cookies, токенов, ключей;
- автоматические деньги, банк, 2FA, security bypass;
- массовый restart/reboot без blast-radius отчета;
- blind install unaudited internet code.


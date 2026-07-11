# Vista OS — Release Security Baseline

## Включить перед публичным релизом

- `VISTA_ENV=production`;
- `VISTA_NODE_JOIN_TOKEN` с длинным случайным значением;
- `VISTA_NODE_SIGNING_SECRET` с длинным случайным значением;
- `VISTA_ALLOWED_ORIGINS` без wildcard;
- TLS reverse proxy;
- регулярный backup `vista.db` и artifact storage;
- systemd hardening для worker-node;
- запрет произвольного shell в node-agent до отдельного verifier gate.

## Runtime policy

- Клиент не видит серверные/factory/API компоненты.
- Node-agent выполняет только known safe task kinds.
- Task completion проходит через verifier.
- Артефакты должны быть непустыми и иметь sha256.
- Dangerous actions требуют approval/verifier.

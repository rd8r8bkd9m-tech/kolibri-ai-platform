# Vista OS 11 architecture

## Product law

1. One entry point and one SPA shell.
2. One active application at a time; no dashboard clutter.
3. Conversation and Command Center invoke capabilities.
4. Role and subscription determine permission; device only changes presentation.
5. The API is the source of product state. UI does not fabricate successful data.

## Runtime layers

```text
React/Vite UI + PWA/Tauri shell
        ↓ signed Vista session
FastAPI Core API
        ↓
SQLite WAL / artifacts / audit ledger
        ↓
Factory queue → lease → node-agent → artifact → verifier
```

## State

A session contains role, plan, device, active estimate, active application and chat. The browser restores the signed session rather than creating a new tenant on every reload.

## Security boundaries

- public roles: client/client_pro;
- privileged roles require owner access token at session creation;
- users only read their own estimates and documents;
- node endpoints use join token plus optional/production-required HMAC signature;
- developer project keys authenticate `/v1/*`; upstream OpenAI keys remain server-side;
- share links are expiring, revocable and scoped to client-visible artifacts.

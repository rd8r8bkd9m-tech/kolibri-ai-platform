# Security Model

- Token env: `KOLIBRI_CHATGPT_ACTION_TOKEN`.
- Gateway health only reports whether a token is configured, never the value.
- Authorization header must match `Bearer <token>` when token is configured.
- Dangerous action markers are blocked before Control Plane proxying.
- Gateway does not print secrets, cookies, keys or tokens.
- Gateway does not directly run shell commands, service restarts, firewall changes or git mutations.

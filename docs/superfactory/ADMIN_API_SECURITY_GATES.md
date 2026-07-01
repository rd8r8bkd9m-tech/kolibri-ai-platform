# Admin API Security Gates

## Назначение

Admin API дает владельцу полный контроль, но каждый опасный запрос проходит safety gates. Это защита фабрики от случайных разрушений, утечек, спама и fake success.

## Gate 1: Authentication

Запрос должен быть привязан к owner/admin session, node identity или service identity. Anonymous admin actions запрещены.

## Gate 2: Authorization

Role must permit action:

- `owner_root`: full-control request, still scoped and logged.
- `command_node`: submit and observe tasks, request owner-approved actions.
- `control_plane`: route and lease tasks.
- `agent_host`: execute leased scoped tasks.
- `remote_agent`: execute task-specific work only.
- `observer`: read-only status.

## Gate 3: Scope

Every write must be limited by `write_scope`. Empty `write_scope` means read-only.

## Gate 4: Constraints

Constraints must be evaluated before execution:

```json
{
  "secrets_redaction_required": true,
  "destructive_git_commands_forbidden": true,
  "git_push_forbidden": true,
  "print_secrets": false,
  "reversible_when_possible": true
}
```

## Gate 5: Audit

Every privileged request logs:

- task_id;
- trace_id;
- owner;
- source;
- command_node;
- requested_role;
- target_node;
- route_used;
- result status;
- artifact references;
- redacted stdout/stderr hashes or summaries.

## Gate 6: Result Integrity

Agent must not claim success unless:

- command finished successfully;
- expected artifacts exist;
- tests/checks listed in acceptance ran or are explicitly unavailable;
- blocked conditions are classified.

## Gate 7: Secret Redaction

Logs, artifacts and owner reports must redact:

- API keys;
- tokens;
- cookies;
- private keys;
- passwords;
- OAuth refresh/access tokens;
- provider credentials.

# Risks And Follow-Ups

Risks:

- The explicit migration command can delete the webhook if an operator intentionally runs it with the approval phrase and a real token.
- Dropping pending updates remains available only as an explicit migration option and should be used only during an owner-approved cutover.

Follow-ups:

- Before any live migration, run the migration command only from the owner-approved operational window.
- Keep the regular `kolibri-telegram-gateway.service` path as the only live receiver.
- Do not add webhook mutation flags to the systemd service or ordinary gateway entrypoint.

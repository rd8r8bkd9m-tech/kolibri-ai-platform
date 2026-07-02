# Risks And Blockers

Blockers:

- Runner timebox violation: the runner did not provide a real 30-minute active work window before artifact generation.
- Missing `httpx` blocks focused wallboard/factory-status pytest execution in this worktree.
- Home terminal wallboard result artifacts are absent for `P0_HOME_FACTORY_TERMINAL_UI_RU_2026_07_01`.
- Telegram gateway remains intentionally inactive/dead in latest canary evidence and needs owner-approved no-mutation diagnostic before any live receiver action.
- GitHub CLI/tooling is missing on at least one control-node path, limiting PR queue metadata classification.

Risks:

- The React wallboard can display misleading confidence if live Control Plane freshness deploy state drifts from checked-in code.
- The owner could see a product UI but still lack the required Home tmux wallboard/attach command.
- Telegram service start/restart without single-receiver proof could create duplicate receiver or webhook/polling conflicts.
- Environment-level dependency repairs can become product-code noise if not handled as an explicit tooling task.
- Earlier failed-useful tasks and later passed canaries coexist; downstream stewards must cite the later evidence when reporting current runtime state.

Safety boundaries observed:

- No secrets or credentials printed.
- No product code changed.
- No services restarted.
- No Telegram API state touched.
- No unrelated work reverted.


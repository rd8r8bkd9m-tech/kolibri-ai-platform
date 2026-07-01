# Business, Guest Bot And Bot-To-Bot Safety Policy

Task: `P0_TELEGRAM_FACTORY_COMMAND_CENTER_SPEC_AND_RUNTIME_GAP_AUDIT_2026_07_01`

## Default State

Business bots, Guest Mode, Bot-to-Bot Communication, Telegram Stars, gifts,
paid media, subscriptions, invoices, and managed bots are disabled by default.

## Activation Requirements

Each feature requires a separate policy PR with:

- threat model
- rate limits
- dedupe
- bounded interaction depth
- per-chat and global quotas
- trace_id/task_id propagation
- audit logs
- kill switch
- owner approval gates

## Hard Blocks

- No spam, fake engagement, fake users, or unsolicited mass outreach.
- No external contact leakage.
- No loop storms between bots.
- No unsupervised money or paid actions.
- No business/customer automation that violates platform rules.
- No exposure of private artifacts, owner project details, participant lists,
  private prompts, or chat history.

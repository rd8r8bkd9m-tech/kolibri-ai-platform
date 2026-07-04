# Rich Streaming Reports Plan

Task: `P0_TELEGRAM_FACTORY_COMMAND_CENTER_SPEC_AND_RUNTIME_GAP_AUDIT_2026_07_01`

## Goal

Use Telegram Bot API 10.1 rich messages for readable factory reports while
keeping a plain text fallback.

## Report Model

Create an internal report model independent of Telegram rendering:

- title
- status
- summary
- task timeline
- PR/CI section
- artifact section
- blocked reasons
- next action
- redacted technical proof

## Telegram Rendering

- Use rich headings, tables, details blocks, artifact lists, and PR/CI links.
- Use thinking/progress blocks only for sanitized task progress, not private
  reasoning.
- Keep raw logs collapsed and redacted.
- Use `sendRichMessageDraft` only behind a feature flag after compatibility is
  proven.
- Fallback to compact `sendMessage` / `editMessageText` text for clients or
  runtimes without rich support.

## Mini App Rendering

The Mini App should render the same normalized report events as cards,
timelines, report drawers, and notification toasts via SSE/WebSocket.

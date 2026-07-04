# Risks And Follow-ups

Risks:

- The formatter is intentionally pattern-based. If remote agents change labels substantially, the card may fall back to the generic owner-task formatter.
- The current parser keeps rollback backup paths only when the line is explicitly marked as rollback or backup.

Follow-ups:

- Ask future GoMesh production-report agents to emit the same stable labels used by this card: Home endpoint, Health, Direct Mbps, GoMesh Mbps, Target, Speed gate, Selector status, pytest, Rollback backup paths, Next action.
- Add another fixture if GoMesh reports start arriving as structured JSON instead of plain text.

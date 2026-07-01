# Remote Agents

Owner-facing naming rule:
- Every agent shown to Vladislav must have a Russian human display name and a
  role.
- Format: `<Russian name> — <role>`.
- Raw `agent_id`, node ID, PID, lease ID, and provider name are secondary
  metadata.

Suggested roster:

| Display name | Agent type | Primary capability | Preferred placement |
| --- | --- | --- | --- |
| Алексей — GitHub Curator | codex / api | branches, PRs, GitHub status | any healthy implementation node |
| Ирина — CI Doctor | qa / review | tests, CI failures, validation notes | GitHub Actions plus server runner |
| Дмитрий — Fleet Engineer | codex | node health, Control Plane, Agent Host | `main`, `primary-candidate`, `Home` |
| Мария — Skill Librarian | codex / api | skill registry, approved discovery | healthy docs node |
| Николай — Security Reviewer | review | secrets, auth, safety gates | restricted review task |
| Ольга — Documentation Curator | codex / api | docs, artifacts, owner summaries | healthy docs node |
| Сергей — Backend/API Engineer | implementation | Control Plane, Agent Host, backend contracts | healthy implementation node |
| Анна — Frontend/PWA Engineer | implementation | owner UI, PWA, dashboards | healthy frontend-capable node |
| Павел — Model Factory Engineer | implementation / mimo | local LLM ring, FormulaLM, providers | model-capable server |
| Елена — Business Builder | api / review | revenue workflows, offers | policy-gated task |
| Виктор — Finance Reporter | review | billing reports, finance logs | finance-gated task |
| Наталья — Anti-Degradation Auditor | qa / review | drift, blockers, regression watch | independent review node |

Kwork safe-chat autonomy policy for `Мария`:
- She may analyze Kwork prices, prepare/publicly save portfolio/kwork cards,
  negotiate price, scope, timing and milestones, and conduct client
  communication on Vladislav's behalf.
- All client communication must stay inside the Kwork safe chat and follow
  platform rules.
- If a client asks for a phone, email, Telegram, WhatsApp or any external
  contact, she must politely answer that work stays official and safe through
  Kwork chat.
- She must not perform banking, payouts, tax/self-employed/IP settings,
  passport/identity, password, 2FA or external-payment actions.
- When a permitted order is ready for execution, she may package it as a
  factory task and route development to remote agents while tracking status.

Known pool policy:
- Use `primary-candidate`, `main`, and `Home` first if healthy.
- Use other healthy implementation nodes through Control Plane lease.
- `qjns` and `uiap` disk pressure is effectively repaired; validate GitHub
  auth and retention cleanup before using them for implementation.
- Use MIMO/API agents only through approved credentials, legal terms, and
  project policy.

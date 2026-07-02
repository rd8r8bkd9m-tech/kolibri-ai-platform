# NEXT

1. Run focused tests and full pytest.
2. Repair write-capable GitHub authentication for the remote server or push this local branch from a node with write access.
3. Open a draft PR from `p0/agent-host-long-runner-lease-heartbeat-repair-2026-07-02-clean`.
4. After deployment, run a 3-task canary before any MIMO or FormulaLM crawler requeue:
   - one direct MIMO task;
   - one Codex/API long runner;
   - one FormulaLM/crawler-like long runner.
5. Requeue the full wave only after canary evidence shows no premature `lease_expired` or `dead_letter`.

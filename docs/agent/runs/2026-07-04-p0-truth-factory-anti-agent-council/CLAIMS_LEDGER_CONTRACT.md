# CLAIMS_LEDGER_CONTRACT.md

**Date:** 2026-07-04T22:40:00Z

## Schema

Every technical statement becomes a claim:

```json
{
  "claim_id": "string",
  "task_id": "string",
  "made_by": "agent_id",
  "claim": "string",
  "scope": "server|task|runner|api|artifact|github|formula_lm|infrastructure",
  "status": "proposed|challenged|verified|rejected|partial|not_proven",
  "evidence": ["evidence_id"],
  "counterclaims": ["claim_id"],
  "verdict": "string",
  "confidence": "high|medium|low",
  "next_action": "string"
}
```

## Example Claims

| claim_id | claim | scope | status | evidence |
|----------|-------|-------|--------|----------|
| C-001 | 21 servers are reachable via SSH | infrastructure | verified | E-001 |
| C-002 | Start Factory works end-to-end | api | verified | E-002, E-003 |
| C-003 | MIMO is available on server-kfrm | runner | verified | E-004 |
| C-004 | Home NOC is green | infrastructure | not_proven | — |
| C-005 | agent-10 is quarantined | server | verified | E-005 |
| C-006 | Fleet has 74/118 nodes online | infrastructure | verified | E-006 |
| C-007 | Running index has 0 drift | api | not_proven | — |
| C-008 | FormulaLM best score is 0.137603 | formula_lm | not_proven | — |

## Rules

1. No claim without evidence
2. Generic completion is never evidence
3. Stale evidence is not evidence
4. Contradictions must be logged
5. Verdict must include confidence level

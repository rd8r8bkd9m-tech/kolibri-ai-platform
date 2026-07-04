# VERDICT_PROTOCOL.md

**Date:** 2026-07-04T22:40:00Z

## Allowed Verdicts

| Verdict | Meaning | Required Evidence |
|---------|---------|-------------------|
| true | Claim fully supported | API response + artifact + test |
| false | Claim contradicted | Counter-evidence |
| partial | Claim partially true | Evidence for true parts, evidence for false parts |
| not_proven | Insufficient evidence | Evidence gap documented |
| blocked | Cannot verify due to dependency | Blocker documented |
| stale | Evidence outdated | Timestamp comparison |
| degraded | Working but not fully | Partial evidence + degradation noted |

## Forbidden

- "done" without proof
- "works" without endpoint/artifact/test
- "available" based only on capability record
- "completed" without collectable artifact
- "verified" without evidence record

## Verdict Record

```json
{
  "verdict_id": "string",
  "claim_id": "string",
  "verdict": "true|false|partial|not_proven|blocked|stale|degraded",
  "confidence": "high|medium|low",
  "evidence": ["evidence_id"],
  "reasoning": "string",
  "next_action": "string",
  "owner_summary": "string"
}
```

## Owner Summary Rule

Owner summary must be:
- 1-2 sentences
- No jargon
- Clear yes/no/partial
- What works, what doesn't, what's next

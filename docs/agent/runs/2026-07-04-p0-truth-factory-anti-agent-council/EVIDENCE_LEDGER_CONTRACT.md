# EVIDENCE_LEDGER_CONTRACT.md

**Date:** 2026-07-04T22:40:00Z

## Schema

```json
{
  "evidence_id": "string",
  "claim_id": "string",
  "type": "api_response|test_result|artifact|github_pr|screenshot|systemd_status|redis_pong|log_excerpt|benchmark_json|checksum|owner_approval",
  "source": "string",
  "timestamp": "ISO8601",
  "content_hash": "sha256",
  "summary": "string",
  "redacted": true,
  "path": "string",
  "valid": true
}
```

## Evidence Types

| Type | Source | Trust Level |
|------|--------|-------------|
| api_response | curl /v1/health | high |
| test_result | pytest output | high |
| artifact | file on disk | high |
| github_pr | gh pr view | high |
| systemd_status | systemctl status | medium |
| redis_pong | redis-cli ping | medium |
| log_excerpt | journalctl | medium |
| benchmark_json | test run | medium |
| screenshot | visual proof | low |
| owner_approval | owner statement | highest |

## Rule

No evidence, no truth.

Every claim must have at least one evidence record with:
- verifiable source
- timestamp
- content hash (for non-trivial evidence)
- valid = true

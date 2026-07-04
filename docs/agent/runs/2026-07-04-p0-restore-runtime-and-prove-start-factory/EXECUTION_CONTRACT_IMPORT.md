# EXECUTION_CONTRACT_IMPORT.md

**Date:** 2026-07-04T22:00:00Z

## Local Repair Available
ops/agent_host.py has execution contract enforcement:
- artifact gate: required artifacts must be readable and non-empty
- generic completion rejection: empty/generic responses rejected
- write_scope gate: checks file write boundaries

## Status
Not yet imported into clean branch. Blocked by:
1. Lease pipeline broken (dual factory-control processes)
2. Need to verify repair works before importing

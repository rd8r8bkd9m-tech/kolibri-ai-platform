# P0 Repair uiap/qjns Disk and Server GitHub Auth

## Context

uiap/qjns disk pressure was observed and server GitHub auth remains a recurring blocker.

## Scope

- Validate disk reserve after cleanup.
- Add retention cleanup.
- Validate noninteractive GitHub fetch/clone without leaking credentials.

## Acceptance

- Node cards report healthy disk reserve.
- GitHub auth works through safe machine identity.
- No secret values appear in logs.

## Forbidden

- No blind deletion.
- No printing keys/tokens/passwords.

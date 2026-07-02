# Skill: Kolibri Server Recovery

## Metadata

| Field | Value |
| --- | --- |
| skill_id | `kolibri-server-recovery` |
| version | `0.1.0` |
| scope | `server` |
| owner | Server Recovery Engineer |
| status | `registered` |

## Purpose

Execute structured node repair procedures without exposing secrets or
making uncontrolled infrastructure changes. Follows the repair taxonomy
from the fleet capability inventory.

## Trigger

- Node marked degraded or unreachable
- Heartbeat freshness repair needed
- Disk pressure detected
- Runner auth failure requiring credential repair

## Inputs

- Node identity and current state
- Blocker classification from fleet inventory
- Repair taxonomy from NODE_BLOCKERS.md
- Owner-approved repair task envelope

## Outputs

- Repair execution report
- Node health restoration confirmation
- Updated node card in Control Plane
- Rollback plan if repair fails

## Safety Constraints

- Never print secrets, tokens, or credentials
- Never repair infrastructure not explicitly in scope
- Never modify production services without rollback plan
- Owner approval required for credential-related repairs
- Bootstrap-only SSH access for recovery

## Dependencies

- Control Plane task dispatch
- Node agent host status
- Fleet inventory blocker data

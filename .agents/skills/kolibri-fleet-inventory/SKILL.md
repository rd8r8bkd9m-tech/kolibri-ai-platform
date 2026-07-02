# Skill: Kolibri Fleet Inventory

## Metadata

| Field | Value |
| --- | --- |
| skill_id | `kolibri-fleet-inventory` |
| version | `0.1.0` |
| scope | `all_agents` |
| owner | Fleet Engineer |
| status | `registered` |

## Purpose

Perform read-only fleet health and capability audits. Classify node cards,
identify blockers, and maintain safe target pools for task dispatch.

## Trigger

- Periodic fleet health check (recommended: daily)
- New node added to Control Plane
- Node heartbeat goes stale
- Task dispatch requires current fleet state

## Inputs

- Control Plane node cards
- Heartbeat freshness data
- Capability signals from agent hosts
- Historical fleet state

## Outputs

- Fleet role matrix (owner-facing, mesh shadow, stale metadata)
- Node blockers report
- Safe target pools by task type
- Next repair tasks

## Safety Constraints

- Read-only: no mutations to any node
- No credential disclosure
- No infrastructure changes
- Report stale cards without attempting repair

## Dependencies

- Control Plane health endpoint
- Node heartbeat data
- Repository fleet documentation

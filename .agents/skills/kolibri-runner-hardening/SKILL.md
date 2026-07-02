# Skill: Kolibri Runner Hardening

## Metadata

| Field | Value |
| --- | --- |
| skill_id | `kolibri-runner-hardening` |
| version | `0.1.0` |
| scope | `server` |
| owner | Runner Hardening Engineer |
| status | `registered` |

## Purpose

Harden AI runner contracts across Kolibri Factory nodes. Ensures runner auth,
output sanitization, permission pack enforcement, and fallback taxonomy are
consistent and secure.

## Trigger

- Runner auth failure detected on any node
- New runner type added to `SUPPORTED_AI_RUNNERS`
- Permission pack contract violation
- Post-merge canary failure related to runner

## Inputs

- Node identity and runner type
- Current runner auth status
- Permission pack classification
- Task envelope with runner request

## Outputs

- Runner auth verification report
- Permission pack gate result
- Runner selection recommendation
- Hardening patch or config change (docs-only or code)

## Safety Constraints

- Never print secrets, tokens, or credentials
- Never modify production runner configs without owner approval
- Never bypass auth checks
- Read-only probes preferred for initial diagnosis

## Dependencies

- `ops/factory_control.py` runner policy
- `ops/agent_host.py` permission pack classifier
- Control Plane health endpoint

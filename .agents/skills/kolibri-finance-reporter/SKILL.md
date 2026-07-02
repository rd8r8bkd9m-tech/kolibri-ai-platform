# Skill: Kolibri Finance Reporter

## Metadata

| Field | Value |
| --- | --- |
| skill_id | `kolibri-finance-reporter` |
| version | `0.1.0` |
| scope | `dev` |
| owner | Finance Reporter |
| status | `registered` |

## Purpose

Generate financial reports, cost tracking, and budget analysis for Kolibri
Factory operations. Track compute costs, API usage, and revenue metrics.

## Trigger

- Monthly reporting cycle
- Cost threshold exceeded
- Revenue milestone reached
- Owner requests financial summary

## Inputs

- Compute usage metrics
- API cost data
- Revenue records
- Budget targets

## Outputs

- Cost breakdown by category
- Revenue vs cost analysis
- Budget variance report
- Cost optimization recommendations

## Safety Constraints

- No access to bank accounts or payment systems
- No automatic money movement
- Financial data never printed in logs
- Owner approval required for all financial actions
- No deceptive financial reporting

## Dependencies

- Compute usage metrics from Control Plane
- API provider billing data
- Revenue tracking records

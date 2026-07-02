# Existing Control Plane Task IDs

Source checked: `P0_REVENUE_PROCESS_SUPERVISOR_FROM_MONETIZATION_ANALYSIS_2026_07_02`.

The supervisor already created the follow-up revenue tasks below. This recovery must not submit duplicates.

| Task id | Observed state on recovery check | Observed lease owner |
| --- | --- | --- |
| `P0_REVENUE_LANDING_AND_OFFER_COPY_2026_07_02` | failed | `mesh-agent-01:agent-host-mesh-agent-01` |
| `P0_REVENUE_SALES_DECK_AND_ONE_PAGER_2026_07_02` | failed | `mesh-agent-03:agent-host-mesh-agent-03` |
| `P0_REVENUE_PRICING_EXPERIMENTS_2026_07_02` | failed | `mesh-agent-16:agent-host-mesh-agent-16` |
| `P0_REVENUE_CRM_PIPELINE_SCHEMA_2026_07_02` | failed | `mesh-agent-20:agent-host-mesh-agent-20` |
| `P0_REVENUE_LEAD_RESEARCH_QUEUE_2026_07_02` | running | `mesh-agent-08:agent-host-mesh-agent-08` |
| `P0_REVENUE_OUTREACH_DRAFT_PACK_2026_07_02` | failed | `mesh-agent-05:agent-host-mesh-agent-05` |
| `P0_REVENUE_DEMO_SCRIPT_PACK_2026_07_02` | failed | `mesh-agent-02:agent-host-mesh-agent-02` |
| `P0_REVENUE_FULFILLMENT_PLAYBOOK_2026_07_02` | failed | `mesh-agent-14:agent-host-mesh-agent-14` |
| `P0_REVENUE_UNIT_ECONOMICS_COST_DASHBOARD_2026_07_02` | failed | `mesh-agent-07:agent-host-mesh-agent-07` |
| `P0_REVENUE_FIRST_KPI_MONITOR_2026_07_02` | failed | `mesh-agent-12:agent-host-mesh-agent-12` |
| `P0_REPAIR_MONETIZATION_REQUIRED_ARTIFACT_LAYER_2026_07_02` | running | `mesh-agent-17:agent-host-mesh-agent-17` |

Follow-up policy: retry or repair failed follow-ups only with new explicit retry idempotency keys and after inspecting each failed task artifact. Do not create another identical first-wave task set.

import type { VerticalNavigationRegistration } from "@/src/verticals/contracts";

/**
 * Trusted release-time registration for the first commercial vertical pack.
 * The server may enable these identifiers but cannot replace their renderer or
 * introduce executable actions.
 */
export const CONSTRUCTION_ESTIMATES_NAVIGATION = {
  owner: "vertical",
  id: "construction.estimates.workspace",
  verticalId: "construction.estimates",
  label: "Сметы",
  capability: "construction.estimates.workspace",
  entitlement: "construction.estimates.use",
  rendererKey: "construction.estimate.renderer.v1",
  allowedActions: [
    "construction.estimate.open",
    "construction.estimate.create",
  ],
} as const satisfies VerticalNavigationRegistration;

import { CONSTRUCTION_ESTIMATES_NAVIGATION } from "@/src/verticals/construction-estimates/registration";
import type {
  CapabilitySnapshot,
  VerticalNavigationRegistration,
} from "@/src/verticals/contracts";

/**
 * Compile-time release composition. Runtime manifests can only activate an
 * entry already present here; they cannot download UI or arbitrary actions.
 */
export const VERTICAL_NAVIGATION_ALLOWLIST: readonly VerticalNavigationRegistration[] =
  [CONSTRUCTION_ESTIMATES_NAVIGATION];

export const availableVerticalNavigation = ({
  capabilities,
  entitlements,
  rendererKeys,
}: CapabilitySnapshot) => {
  const enabledCapabilities = new Set(capabilities);
  const enabledEntitlements = new Set(entitlements);
  const bundledRenderers = new Set(rendererKeys);
  return VERTICAL_NAVIGATION_ALLOWLIST.filter(
    ({ capability, entitlement, rendererKey }) =>
      enabledCapabilities.has(capability) &&
      enabledEntitlements.has(entitlement) &&
      bundledRenderers.has(rendererKey),
  );
};

import type { MobileUser } from "@/src/auth/mobile-session";
import { availableVerticalNavigation } from "@/src/verticals/registry";

export const CONSTRUCTION_ESTIMATE_RENDERER =
  "construction.estimate.renderer.v1";

export type ConstructionEstimateAccess =
  | { enabled: true }
  | { enabled: false; reason: string };

export const constructionEstimateAccess = (
  user: MobileUser | null,
): ConstructionEstimateAccess => {
  if (!user) return { enabled: false, reason: "Требуется вход в аккаунт." };
  const capabilities = Array.isArray(user.capabilities)
    ? user.capabilities
    : [];
  const entitlements = Array.isArray(user.entitlements)
    ? user.entitlements
    : [];
  const matches = availableVerticalNavigation({
    capabilities,
    entitlements,
    rendererKeys: [CONSTRUCTION_ESTIMATE_RENDERER],
  });
  if (matches.length === 1) return { enabled: true };

  const missing: string[] = [];
  if (!capabilities.includes("construction.estimates.workspace")) {
    missing.push("capability construction.estimates.workspace");
  }
  if (!entitlements.includes("construction.estimates.use")) {
    missing.push("entitlement construction.estimates.use");
  }
  return {
    enabled: false,
    reason: `Сервер ещё не выдал ${missing.join(" и ")}.`,
  };
};

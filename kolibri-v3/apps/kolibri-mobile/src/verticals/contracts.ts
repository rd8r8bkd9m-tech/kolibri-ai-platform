export type CapabilitySnapshot = {
  capabilities: readonly string[];
  entitlements: readonly string[];
  rendererKeys: readonly string[];
};

export type VerticalNavigationRegistration = {
  owner: "vertical";
  id: string;
  verticalId: string;
  label: string;
  capability: string;
  entitlement: string;
  rendererKey: string;
  allowedActions: readonly string[];
};

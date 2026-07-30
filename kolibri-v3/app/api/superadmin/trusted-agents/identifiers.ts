import "server-only";

const WORKSPACE_BINDING_ID = /^wsb_[0-9a-f]{32}$/;
const TRUSTED_AGENT_PROFILE_ID = /^tap_[0-9a-f]{32}$/;

export function isWorkspaceBindingId(value: string) {
  return WORKSPACE_BINDING_ID.test(value);
}

export function isTrustedAgentProfileId(value: string) {
  return TRUSTED_AGENT_PROFILE_ID.test(value);
}

export const AGENT_PROFILES = [
  "auto",
  "mimo-code",
  "codex-cli",
] as const;

export type AgentProfile = (typeof AGENT_PROFILES)[number];
export type AccountRole = "owner" | "user";

export type AccountUser = {
  id: string;
  tenantId: string;
  email: string;
  name: string;
  role: AccountRole;
  isPlatformOwner: boolean;
  capabilities: string[];
  preferredAgentProfile: AgentProfile;
  preferredModel: string | null;
  preferredReasoningEffort: string | null;
  preferredServiceTier: string | null;
};

export type AccountSession = {
  authenticated: boolean;
  user: AccountUser | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readString(
  value: Record<string, unknown>,
  camelName: string,
  snakeName = camelName,
) {
  const candidate = value[camelName] ?? value[snakeName];
  return typeof candidate === "string" ? candidate.trim() : "";
}

export function isAgentProfile(value: unknown): value is AgentProfile {
  return (
    typeof value === "string" &&
    (AGENT_PROFILES as readonly string[]).includes(value)
  );
}

const SAFE_MODEL_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/;
const SAFE_REASONING_EFFORT = /^[a-z0-9][a-z0-9_-]{0,31}$/;
const SAFE_SERVICE_TIER = /^[a-z0-9][a-z0-9_-]{0,31}$/;

function optionalSafeValue(
  value: unknown,
  pattern: RegExp,
): string | null | undefined {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string") return undefined;
  const normalized = value.trim();
  return pattern.test(normalized) ? normalized : undefined;
}

export function sanitizeAccountUser(value: unknown): AccountUser | null {
  if (!isRecord(value)) return null;

  const id = readString(value, "id");
  const tenantId = readString(value, "tenantId", "tenant_id");
  const email = readString(value, "email").toLowerCase();
  const name = readString(value, "name");
  const role = readString(value, "role");
  const isPlatformOwner =
    value.isPlatformOwner ?? value.is_platform_owner;
  const capabilities = value.capabilities;
  const preferredAgentProfile =
    value.preferredAgentProfile ?? value.preferred_agent_profile;
  const preferredModel = optionalSafeValue(
    value.preferredModel ?? value.preferred_model,
    SAFE_MODEL_ID,
  );
  const preferredReasoningEffort = optionalSafeValue(
    value.preferredReasoningEffort ??
      value.preferred_reasoning_effort,
    SAFE_REASONING_EFFORT,
  );
  const preferredServiceTier = optionalSafeValue(
    value.preferredServiceTier ?? value.preferred_service_tier,
    SAFE_SERVICE_TIER,
  );

  if (
    id.length < 8 ||
    id.length > 160 ||
    tenantId.length < 8 ||
    tenantId.length > 160 ||
    email.length < 3 ||
    email.length > 320 ||
    !email.includes("@") ||
    name.length < 1 ||
    name.length > 160 ||
    (role !== "owner" && role !== "user") ||
    typeof isPlatformOwner !== "boolean" ||
    isPlatformOwner !== (role === "owner") ||
    !Array.isArray(capabilities) ||
    capabilities.length > 32 ||
    capabilities.some(
      (capability) =>
        typeof capability !== "string" ||
        !/^[a-z][a-z0-9._-]{1,95}$/.test(capability),
    ) ||
    new Set(capabilities).size !== capabilities.length ||
    !isAgentProfile(preferredAgentProfile) ||
    preferredModel === undefined ||
    preferredReasoningEffort === undefined ||
    preferredServiceTier === undefined
  ) {
    return null;
  }

  return {
    id,
    tenantId,
    email,
    name,
    role,
    isPlatformOwner,
    capabilities: capabilities as string[],
    preferredAgentProfile,
    preferredModel,
    preferredReasoningEffort,
    preferredServiceTier,
  };
}

export function sanitizeAccountSession(value: unknown): AccountSession | null {
  if (!isRecord(value) || typeof value.authenticated !== "boolean") {
    return null;
  }

  if (!value.authenticated) {
    return value.user === null || value.user === undefined
      ? { authenticated: false, user: null }
      : null;
  }

  const user = sanitizeAccountUser(value.user);
  return user ? { authenticated: true, user } : null;
}

export function accountInitials(user: AccountUser | null) {
  if (!user) return "К";
  const parts = user.name
    .split(/\s+/)
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length === 0) return "К";
  return parts
    .slice(0, 2)
    .map((part) => part[0]?.toLocaleUpperCase("ru-RU") ?? "")
    .join("");
}

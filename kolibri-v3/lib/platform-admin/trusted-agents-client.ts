"use client";

import {
  boundedText,
  integer,
  isRecord,
  platformAdminRequest,
  type PlatformAdminPage,
} from "@/lib/platform-admin/client";

const WORKSPACE_BINDING_ID = /^wsb_[0-9a-f]{32}$/;
const WORKSPACE_SERVER_REF = /^wsref_[0-9a-f]{32}$/;
const TRUSTED_AGENT_PROFILE_ID = /^tap_[0-9a-f]{32}$/;
const TRUSTED_AGENT_AUDIT_ID = /^taudit_[0-9a-f]{32}$/;
const TRUSTED_AGENT_AUDIT_CURSOR =
  /^(0|[1-9][0-9]{0,19}):taudit_[0-9a-f]{32}$/;
const FINGERPRINT_TOKEN = /^sha256:[0-9a-f]{64}$/;
const RUNTIME_PROFILE = /^[a-z0-9][a-z0-9._-]{1,95}$/;
const AGENT_CARD_ID = /^[a-z0-9][a-z0-9._-]{2,127}$/;
const PAGE_SIZE = 50;
const MAX_PAGE_SIZE = 100;

export type TrustedAgentEnvironment =
  | "development"
  | "staging"
  | "production";
export type TrustedAgentLifecycleStatus = "active" | "revoked";
export type TrustedAgentAuditAction =
  | "binding.created"
  | "binding.updated"
  | "binding.revoked"
  | "profile.created"
  | "profile.updated"
  | "profile.revoked"
  | "profile.revoked_by_binding";

export type TrustedAgentWorkspaceBinding = {
  id: string;
  serverRef: string;
  environment: TrustedAgentEnvironment;
  fingerprintToken: string;
  authorityEpoch: number;
  lifecycleStatus: TrustedAgentLifecycleStatus;
  workspaceEpoch: number;
  revision: number;
  createdAt: number;
  updatedAt: number;
  revokedAt: number | null;
};

export type TrustedAgentProfile = {
  id: string;
  workspaceBindingId: string;
  workspaceBindingEpoch: number;
  displayName: string;
  runtimeProfile: string;
  agentCardId: string;
  agentCardVersion: number;
  capabilities: ["developer.runtime.execute"];
  toolPolicyId: "developer.full.v1";
  accessMode: "full";
  sandboxProfile: "danger-full-access";
  approvalPolicy: "never";
  approvalsReviewer: null;
  maxConcurrency: 1;
  authorityEpoch: number;
  lifecycleStatus: TrustedAgentLifecycleStatus;
  profileEpoch: number;
  revision: number;
  createdAt: number;
  updatedAt: number;
  revokedAt: number | null;
};

export type CreateTrustedAgentWorkspaceBinding = {
  environment: TrustedAgentEnvironment;
  fingerprintToken: string;
};

export type CreateTrustedAgentProfile = {
  workspaceBindingId: string;
  displayName: string;
  runtimeProfile: string;
  agentCardId: string;
  agentCardVersion: number;
};

export type TrustedAgentAuditEvent = {
  id: string;
  action: TrustedAgentAuditAction;
  targetType: "binding" | "profile";
  targetId: string;
  targetRevision: number;
  targetEpoch: number;
  authorityEpoch: number;
  createdAt: number;
};

const isEnvironment = (
  value: unknown,
): value is TrustedAgentEnvironment =>
  value === "development" ||
  value === "staging" ||
  value === "production";

const isLifecycleStatus = (
  value: unknown,
): value is TrustedAgentLifecycleStatus =>
  value === "active" || value === "revoked";

const exactToken = (value: unknown, expression: RegExp) =>
  typeof value === "string" && expression.test(value) ? value : null;

const nullableInteger = (
  value: unknown,
  minimum: number,
  maximum: number,
) => (value === null ? null : integer(value, minimum, maximum));

const displayName = (value: unknown) => {
  const normalized = boundedText(value, 120);
  if (
    !normalized ||
    normalized.includes("/") ||
    normalized.includes("\\") ||
    normalized.includes("://") ||
    normalized.startsWith("~") ||
    Array.from(normalized).some((character) => character.charCodeAt(0) < 32)
  ) {
    return null;
  }
  return normalized;
};

function parseWorkspaceBinding(
  value: unknown,
): TrustedAgentWorkspaceBinding | null {
  if (!isRecord(value)) return null;
  const id = exactToken(value.id, WORKSPACE_BINDING_ID);
  const serverRef = exactToken(value.serverRef, WORKSPACE_SERVER_REF);
  const fingerprintToken = exactToken(
    value.fingerprintToken,
    FINGERPRINT_TOKEN,
  );
  const authorityEpoch = integer(
    value.authorityEpoch,
    1,
    Number.MAX_SAFE_INTEGER,
  );
  const workspaceEpoch = integer(
    value.workspaceEpoch,
    1,
    Number.MAX_SAFE_INTEGER,
  );
  const revision = integer(value.revision, 1, Number.MAX_SAFE_INTEGER);
  const createdAt = integer(value.createdAt, 0, Number.MAX_SAFE_INTEGER);
  const updatedAt = integer(value.updatedAt, 0, Number.MAX_SAFE_INTEGER);
  const revokedAt = nullableInteger(
    value.revokedAt,
    0,
    Number.MAX_SAFE_INTEGER,
  );
  if (
    !id ||
    !serverRef ||
    !isEnvironment(value.environment) ||
    !fingerprintToken ||
    authorityEpoch === null ||
    !isLifecycleStatus(value.lifecycleStatus) ||
    workspaceEpoch === null ||
    revision === null ||
    createdAt === null ||
    updatedAt === null ||
    revokedAt === null !== (value.revokedAt === null) ||
    (value.lifecycleStatus === "active" && value.revokedAt !== null) ||
    (value.lifecycleStatus === "revoked" && value.revokedAt === null)
  ) {
    return null;
  }
  return {
    id,
    serverRef,
    environment: value.environment,
    fingerprintToken,
    authorityEpoch,
    lifecycleStatus: value.lifecycleStatus,
    workspaceEpoch,
    revision,
    createdAt,
    updatedAt,
    revokedAt,
  };
}

function parseTrustedAgentProfile(
  value: unknown,
): TrustedAgentProfile | null {
  if (!isRecord(value)) return null;
  const id = exactToken(value.id, TRUSTED_AGENT_PROFILE_ID);
  const workspaceBindingId = exactToken(
    value.workspaceBindingId,
    WORKSPACE_BINDING_ID,
  );
  const normalizedDisplayName = displayName(value.displayName);
  const runtimeProfile = exactToken(value.runtimeProfile, RUNTIME_PROFILE);
  const agentCardId = exactToken(value.agentCardId, AGENT_CARD_ID);
  const workspaceBindingEpoch = integer(
    value.workspaceBindingEpoch,
    1,
    Number.MAX_SAFE_INTEGER,
  );
  const agentCardVersion = integer(
    value.agentCardVersion,
    1,
    2_147_483_647,
  );
  const authorityEpoch = integer(
    value.authorityEpoch,
    1,
    Number.MAX_SAFE_INTEGER,
  );
  const profileEpoch = integer(
    value.profileEpoch,
    1,
    Number.MAX_SAFE_INTEGER,
  );
  const revision = integer(value.revision, 1, Number.MAX_SAFE_INTEGER);
  const createdAt = integer(value.createdAt, 0, Number.MAX_SAFE_INTEGER);
  const updatedAt = integer(value.updatedAt, 0, Number.MAX_SAFE_INTEGER);
  const revokedAt = nullableInteger(
    value.revokedAt,
    0,
    Number.MAX_SAFE_INTEGER,
  );
  if (
    !id ||
    !workspaceBindingId ||
    workspaceBindingEpoch === null ||
    !normalizedDisplayName ||
    !runtimeProfile ||
    !agentCardId ||
    agentCardVersion === null ||
    !Array.isArray(value.capabilities) ||
    value.capabilities.length !== 1 ||
    value.capabilities[0] !== "developer.runtime.execute" ||
    value.toolPolicyId !== "developer.full.v1" ||
    value.accessMode !== "full" ||
    value.sandboxProfile !== "danger-full-access" ||
    value.approvalPolicy !== "never" ||
    value.approvalsReviewer !== null ||
    value.maxConcurrency !== 1 ||
    authorityEpoch === null ||
    !isLifecycleStatus(value.lifecycleStatus) ||
    profileEpoch === null ||
    revision === null ||
    createdAt === null ||
    updatedAt === null ||
    revokedAt === null !== (value.revokedAt === null) ||
    (value.lifecycleStatus === "active" && value.revokedAt !== null) ||
    (value.lifecycleStatus === "revoked" && value.revokedAt === null)
  ) {
    return null;
  }
  return {
    id,
    workspaceBindingId,
    workspaceBindingEpoch,
    displayName: normalizedDisplayName,
    runtimeProfile,
    agentCardId,
    agentCardVersion,
    capabilities: ["developer.runtime.execute"],
    toolPolicyId: "developer.full.v1",
    accessMode: "full",
    sandboxProfile: "danger-full-access",
    approvalPolicy: "never",
    approvalsReviewer: null,
    maxConcurrency: 1,
    authorityEpoch,
    lifecycleStatus: value.lifecycleStatus,
    profileEpoch,
    revision,
    createdAt,
    updatedAt,
    revokedAt,
  };
}

function parseTrustedAgentAuditEvent(
  value: unknown,
): TrustedAgentAuditEvent | null {
  if (!isRecord(value) || !isRecord(value.before) || !isRecord(value.after)) {
    return null;
  }
  const id = exactToken(value.id, TRUSTED_AGENT_AUDIT_ID);
  const targetId =
    value.targetType === "binding"
      ? exactToken(value.targetId, WORKSPACE_BINDING_ID)
      : value.targetType === "profile"
        ? exactToken(value.targetId, TRUSTED_AGENT_PROFILE_ID)
        : null;
  const targetRevision = integer(
    value.targetRevision,
    1,
    Number.MAX_SAFE_INTEGER,
  );
  const targetEpoch = integer(value.targetEpoch, 1, Number.MAX_SAFE_INTEGER);
  const authorityEpoch = integer(
    value.authorityEpoch,
    1,
    Number.MAX_SAFE_INTEGER,
  );
  const createdAt = integer(value.createdAt, 0, Number.MAX_SAFE_INTEGER);
  const actions: readonly TrustedAgentAuditAction[] = [
    "binding.created",
    "binding.updated",
    "binding.revoked",
    "profile.created",
    "profile.updated",
    "profile.revoked",
    "profile.revoked_by_binding",
  ];
  if (
    !id ||
    !actions.includes(value.action as TrustedAgentAuditAction) ||
    (value.targetType !== "binding" && value.targetType !== "profile") ||
    !targetId ||
    targetRevision === null ||
    targetEpoch === null ||
    authorityEpoch === null ||
    createdAt === null
  ) {
    return null;
  }
  return {
    id,
    action: value.action as TrustedAgentAuditAction,
    targetType: value.targetType,
    targetId,
    targetRevision,
    targetEpoch,
    authorityEpoch,
    createdAt,
  };
}

function parsePage<T>(
  value: unknown,
  parseItem: (item: unknown) => T | null,
  cursorExpression: RegExp,
): PlatformAdminPage<T> {
  if (
    !isRecord(value) ||
    !Array.isArray(value.items) ||
    value.items.length > MAX_PAGE_SIZE
  ) {
    throw new Error("Контур доверенных агентов вернул некорректный список.");
  }
  const items = value.items.map(parseItem);
  if (items.some((item) => item === null)) {
    throw new Error("Контур доверенных агентов вернул некорректный список.");
  }
  const nextCursor =
    value.nextCursor === null
      ? null
      : exactToken(value.nextCursor, cursorExpression);
  if (value.nextCursor !== null && nextCursor === null) {
    throw new Error("Контур доверенных агентов вернул некорректный cursor.");
  }
  return {
    items: items as T[],
    nextCursor,
  };
}

const pagePath = (
  resource: "workspace-bindings" | "profiles",
  cursor?: string,
) => {
  const parameters = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (cursor) parameters.set("cursor", cursor);
  return `/api/superadmin/trusted-agents/${resource}?${parameters.toString()}`;
};

export async function getTrustedAgentWorkspaceBindingsPage(
  cursor?: string,
  signal?: AbortSignal,
): Promise<PlatformAdminPage<TrustedAgentWorkspaceBinding>> {
  if (cursor && !WORKSPACE_BINDING_ID.test(cursor)) {
    throw new Error("Некорректный cursor привязок.");
  }
  return parsePage(
    await platformAdminRequest(pagePath("workspace-bindings", cursor), {
      signal,
    }),
    parseWorkspaceBinding,
    WORKSPACE_BINDING_ID,
  );
}

export async function getTrustedAgentProfilesPage(
  cursor?: string,
  signal?: AbortSignal,
): Promise<PlatformAdminPage<TrustedAgentProfile>> {
  if (cursor && !TRUSTED_AGENT_PROFILE_ID.test(cursor)) {
    throw new Error("Некорректный cursor профилей.");
  }
  return parsePage(
    await platformAdminRequest(pagePath("profiles", cursor), { signal }),
    parseTrustedAgentProfile,
    TRUSTED_AGENT_PROFILE_ID,
  );
}

export async function getTrustedAgentAuditPage(
  cursor?: string,
  signal?: AbortSignal,
): Promise<PlatformAdminPage<TrustedAgentAuditEvent>> {
  if (cursor && !TRUSTED_AGENT_AUDIT_CURSOR.test(cursor)) {
    throw new Error("Некорректный cursor журнала агентов.");
  }
  const parameters = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (cursor) parameters.set("cursor", cursor);
  return parsePage(
    await platformAdminRequest(
      `/api/superadmin/trusted-agents/audit?${parameters.toString()}`,
      { signal },
    ),
    parseTrustedAgentAuditEvent,
    TRUSTED_AGENT_AUDIT_CURSOR,
  );
}

export async function createTrustedAgentWorkspaceBinding(
  input: CreateTrustedAgentWorkspaceBinding,
): Promise<TrustedAgentWorkspaceBinding> {
  if (!isEnvironment(input.environment)) {
    throw new Error("Некорректное окружение рабочего пространства.");
  }
  const fingerprintToken = exactToken(
    input.fingerprintToken,
    FINGERPRINT_TOKEN,
  );
  if (!fingerprintToken) {
    throw new Error("Некорректный fingerprint рабочего пространства.");
  }
  const value = await platformAdminRequest(
    "/api/superadmin/trusted-agents/workspace-bindings",
    {
      method: "POST",
      body: JSON.stringify({
        environment: input.environment,
        fingerprintToken,
      }),
    },
  );
  const binding = parseWorkspaceBinding(value);
  if (!binding) {
    throw new Error("Backend вернул некорректную привязку.");
  }
  return binding;
}

export async function createTrustedAgentProfile(
  input: CreateTrustedAgentProfile,
): Promise<TrustedAgentProfile> {
  const workspaceBindingId = exactToken(
    input.workspaceBindingId,
    WORKSPACE_BINDING_ID,
  );
  const normalizedDisplayName = displayName(input.displayName);
  const runtimeProfile = exactToken(
    input.runtimeProfile,
    RUNTIME_PROFILE,
  );
  const agentCardId = exactToken(input.agentCardId, AGENT_CARD_ID);
  const agentCardVersion = integer(
    input.agentCardVersion,
    1,
    2_147_483_647,
  );
  if (
    !workspaceBindingId ||
    !normalizedDisplayName ||
    !runtimeProfile ||
    !agentCardId ||
    agentCardVersion === null
  ) {
    throw new Error("Некорректные настройки доверенного агента.");
  }
  const value = await platformAdminRequest(
    "/api/superadmin/trusted-agents/profiles",
    {
      method: "POST",
      body: JSON.stringify({
        workspaceBindingId,
        displayName: normalizedDisplayName,
        runtimeProfile,
        agentCardId,
        agentCardVersion,
        accessMode: "full",
        sandboxProfile: "danger-full-access",
        approvalPolicy: "never",
        maxConcurrency: 1,
      }),
    },
  );
  const profile = parseTrustedAgentProfile(value);
  if (!profile) {
    throw new Error("Backend вернул некорректный профиль агента.");
  }
  return profile;
}

export async function revokeTrustedAgentWorkspaceBinding(
  bindingId: string,
  revision: number,
): Promise<TrustedAgentWorkspaceBinding> {
  if (!WORKSPACE_BINDING_ID.test(bindingId)) {
    throw new Error("Некорректный ID привязки.");
  }
  const expectedRevision = integer(revision, 1, Number.MAX_SAFE_INTEGER);
  if (expectedRevision === null) {
    throw new Error("Некорректная ревизия привязки.");
  }
  const value = await platformAdminRequest(
    `/api/superadmin/trusted-agents/workspace-bindings/${bindingId}/revoke`,
    {
      method: "POST",
      body: JSON.stringify({ revision: expectedRevision }),
    },
  );
  const binding = parseWorkspaceBinding(value);
  if (!binding || binding.id !== bindingId) {
    throw new Error("Backend вернул некорректную привязку.");
  }
  return binding;
}

export async function revokeTrustedAgentProfile(
  profileId: string,
  revision: number,
): Promise<TrustedAgentProfile> {
  if (!TRUSTED_AGENT_PROFILE_ID.test(profileId)) {
    throw new Error("Некорректный ID профиля.");
  }
  const expectedRevision = integer(revision, 1, Number.MAX_SAFE_INTEGER);
  if (expectedRevision === null) {
    throw new Error("Некорректная ревизия профиля.");
  }
  const value = await platformAdminRequest(
    `/api/superadmin/trusted-agents/profiles/${profileId}/revoke`,
    {
      method: "POST",
      body: JSON.stringify({ revision: expectedRevision }),
    },
  );
  const profile = parseTrustedAgentProfile(value);
  if (!profile || profile.id !== profileId) {
    throw new Error("Backend вернул некорректный профиль агента.");
  }
  return profile;
}

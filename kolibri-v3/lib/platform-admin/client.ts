"use client";

import { withCsrfHeader } from "@/lib/csrf";

const MAX_RESPONSE_BYTES = 2 * 1024 * 1024;
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._~-]{0,159}$/;
const SAFE_POLICY_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/;
const SAFE_AUDIT_CURSOR =
  /^(0|[1-9][0-9]{0,19}):[A-Za-z0-9._~-]{1,160}$/;

export type TenantPolicy = {
  lifecycleStatus: "active" | "suspended";
  planCode: string;
  userLimit: number | null;
  monthlyRunLimit: number | null;
  developerAccessEnabled: boolean;
  allowedModelIds: string[] | null;
  allowedProviderIds: string[] | null;
  blockReason: string | null;
  revision: number;
  updatedAt: number;
};

export type PlatformTenant = {
  id: string;
  name: string;
  createdAt: number;
  userCount: number;
  activeSessionCount: number;
  policy: TenantPolicy;
};

export type UserControl = {
  accessStatus: "active" | "blocked";
  developerAccess: "inherit" | "allow" | "deny";
  blockReason: string | null;
  revision: number;
  updatedAt: number;
};

export type PlatformUser = {
  id: string;
  tenantId: string;
  email: string;
  name: string;
  role: "owner" | "user";
  isPlatformOwner: boolean;
  createdAt: number;
  updatedAt: number;
  activeSessionCount: number;
  control: UserControl;
};

export type PlatformAuditEvent = {
  id: string;
  actorUserId: string;
  action: string;
  targetType: "tenant" | "user" | "sessions" | "policy";
  targetId: string;
  targetTenantId: string;
  createdAt: number;
};

export type TenantPolicyUpdate = {
  revision: number;
  lifecycleStatus?: "active" | "suspended";
  planCode?: string;
  userLimit?: number | null;
  monthlyRunLimit?: number | null;
  developerAccessEnabled?: boolean;
  allowedModelIds?: string[] | null;
  allowedProviderIds?: string[] | null;
  blockReason?: string | null;
};

export type UserControlUpdate = {
  revision: number;
  accessStatus?: "active" | "blocked";
  developerAccess?: "inherit" | "allow" | "deny";
  blockReason?: string | null;
};

export const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export const boundedText = (value: unknown, maximum: number) =>
  typeof value === "string" &&
  value.trim().length > 0 &&
  value.trim().length <= maximum
    ? value.trim()
    : null;

export const integer = (
  value: unknown,
  minimum: number,
  maximum: number,
): number | null =>
  typeof value === "number" &&
  Number.isSafeInteger(value) &&
  value >= minimum &&
  value <= maximum
    ? value
    : null;

const nullableInteger = (
  value: unknown,
  minimum: number,
  maximum: number,
) => (value === null ? null : integer(value, minimum, maximum));

const nullableText = (value: unknown, maximum: number) =>
  value === null ? null : boundedText(value, maximum);

const policyIds = (value: unknown): string[] | null | undefined => {
  if (value === null) return null;
  if (
    !Array.isArray(value) ||
    value.length > 256 ||
    value.some(
      (item) =>
        typeof item !== "string" ||
        !SAFE_POLICY_ID.test(item) ||
        item.length > 120,
    )
  ) {
    return undefined;
  }
  const values = value as string[];
  return new Set(values).size === values.length ? values : undefined;
};

function parseTenant(value: unknown): PlatformTenant | null {
  if (!isRecord(value) || !isRecord(value.policy)) return null;
  const policy = value.policy;
  const id = boundedText(value.id, 160);
  const name = boundedText(value.name, 160);
  const planCode = boundedText(policy.planCode, 48);
  const allowedModelIds = policyIds(policy.allowedModelIds);
  const allowedProviderIds = policyIds(policy.allowedProviderIds);
  const userLimit = nullableInteger(policy.userLimit, 1, 1_000_000);
  const monthlyRunLimit = nullableInteger(
    policy.monthlyRunLimit,
    0,
    1_000_000_000,
  );
  const blockReason = nullableText(policy.blockReason, 500);
  if (
    !id ||
    !SAFE_ID.test(id) ||
    !name ||
    !planCode ||
    (policy.lifecycleStatus !== "active" &&
      policy.lifecycleStatus !== "suspended") ||
    typeof policy.developerAccessEnabled !== "boolean" ||
    allowedModelIds === undefined ||
    allowedProviderIds === undefined ||
    userLimit === null !== (policy.userLimit === null) ||
    monthlyRunLimit === null !== (policy.monthlyRunLimit === null) ||
    blockReason === null !== (policy.blockReason === null) ||
    integer(policy.revision, 1, Number.MAX_SAFE_INTEGER) === null ||
    integer(policy.updatedAt, 0, Number.MAX_SAFE_INTEGER) === null ||
    integer(value.createdAt, 0, Number.MAX_SAFE_INTEGER) === null ||
    integer(value.userCount, 0, 1_000_000) === null ||
    integer(value.activeSessionCount, 0, 1_000_000) === null
  ) {
    return null;
  }
  return {
    id,
    name,
    createdAt: value.createdAt as number,
    userCount: value.userCount as number,
    activeSessionCount: value.activeSessionCount as number,
    policy: {
      lifecycleStatus: policy.lifecycleStatus,
      planCode,
      userLimit: policy.userLimit as number | null,
      monthlyRunLimit: policy.monthlyRunLimit as number | null,
      developerAccessEnabled: policy.developerAccessEnabled,
      allowedModelIds,
      allowedProviderIds,
      blockReason,
      revision: policy.revision as number,
      updatedAt: policy.updatedAt as number,
    },
  };
}

function parseUser(value: unknown): PlatformUser | null {
  if (!isRecord(value) || !isRecord(value.control)) return null;
  const control = value.control;
  const id = boundedText(value.id, 160);
  const tenantId = boundedText(value.tenantId, 160);
  const email = boundedText(value.email, 320);
  const name = boundedText(value.name, 160);
  const blockReason = nullableText(control.blockReason, 500);
  if (
    !id ||
    !tenantId ||
    !SAFE_ID.test(id) ||
    !SAFE_ID.test(tenantId) ||
    !email ||
    !email.includes("@") ||
    !name ||
    (value.role !== "owner" && value.role !== "user") ||
    typeof value.isPlatformOwner !== "boolean" ||
    (control.accessStatus !== "active" &&
      control.accessStatus !== "blocked") ||
    !["inherit", "allow", "deny"].includes(
      String(control.developerAccess),
    ) ||
    blockReason === null !== (control.blockReason === null) ||
    integer(control.revision, 1, Number.MAX_SAFE_INTEGER) === null ||
    integer(control.updatedAt, 0, Number.MAX_SAFE_INTEGER) === null ||
    integer(value.createdAt, 0, Number.MAX_SAFE_INTEGER) === null ||
    integer(value.updatedAt, 0, Number.MAX_SAFE_INTEGER) === null ||
    integer(value.activeSessionCount, 0, 1_000_000) === null
  ) {
    return null;
  }
  return {
    id,
    tenantId,
    email,
    name,
    role: value.role,
    isPlatformOwner: value.isPlatformOwner,
    createdAt: value.createdAt as number,
    updatedAt: value.updatedAt as number,
    activeSessionCount: value.activeSessionCount as number,
    control: {
      accessStatus: control.accessStatus,
      developerAccess: control.developerAccess as UserControl["developerAccess"],
      blockReason,
      revision: control.revision as number,
      updatedAt: control.updatedAt as number,
    },
  };
}

function parseAuditEvent(value: unknown): PlatformAuditEvent | null {
  if (!isRecord(value)) return null;
  const id = boundedText(value.id, 160);
  const actorUserId = boundedText(value.actorUserId, 160);
  const action = boundedText(value.action, 120);
  const targetId = boundedText(value.targetId, 160);
  const targetTenantId = boundedText(value.targetTenantId, 160);
  if (
    !id ||
    !actorUserId ||
    !action ||
    !targetId ||
    !targetTenantId ||
    !["tenant", "user", "sessions", "policy"].includes(
      String(value.targetType),
    ) ||
    integer(value.createdAt, 0, Number.MAX_SAFE_INTEGER) === null
  ) {
    return null;
  }
  return {
    id,
    actorUserId,
    action,
    targetType: value.targetType as PlatformAuditEvent["targetType"],
    targetId,
    targetTenantId,
    createdAt: value.createdAt as number,
  };
}

async function responsePayload(response: Response): Promise<unknown> {
  const declared = Number(response.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > MAX_RESPONSE_BYTES) {
    throw new Error("Ответ панели управления слишком большой.");
  }
  const text = await response.text();
  if (new TextEncoder().encode(text).byteLength > MAX_RESPONSE_BYTES) {
    throw new Error("Ответ панели управления слишком большой.");
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new Error("Панель управления вернула некорректный ответ.");
  }
}

export async function platformAdminRequest(
  path: string,
  init: RequestInit = {},
) {
  const response = await fetch(path, {
    ...init,
    headers:
      init.method && init.method !== "GET"
        ? withCsrfHeader({
            Accept: "application/json",
            "Content-Type": "application/json",
            ...init.headers,
          })
        : { Accept: "application/json", ...init.headers },
    credentials: "same-origin",
    cache: "no-store",
  });
  const payload = await responsePayload(response);
  if (!response.ok) {
    const message =
      isRecord(payload) && typeof payload.message === "string"
        ? payload.message
        : "Действие панели управления не выполнено.";
    throw new Error(message);
  }
  return payload;
}

function parsePage<T>(
  value: unknown,
  parser: (item: unknown) => T | null,
  cursor: { maximum: number; pattern: RegExp } = {
    maximum: 160,
    pattern: SAFE_ID,
  },
): { items: T[]; nextCursor: string | null } {
  if (!isRecord(value) || !Array.isArray(value.items)) {
    throw new Error("Панель управления вернула некорректный список.");
  }
  const items = value.items.slice(0, 100).map(parser);
  if (items.some((item) => item === null)) {
    throw new Error("Панель управления вернула некорректный список.");
  }
  const nextCursor =
    value.nextCursor === null
      ? null
      : boundedText(value.nextCursor, cursor.maximum);
  if (
    value.nextCursor !== null &&
    (!nextCursor || !cursor.pattern.test(nextCursor))
  ) {
    throw new Error("Панель управления вернула некорректный cursor.");
  }
  return { items: items as T[], nextCursor };
}

export type PlatformAdminPage<T> = {
  items: T[];
  nextCursor: string | null;
};

const pagePath = (resource: "tenants" | "users" | "audit", limit: number, cursor?: string) => {
  const parameters = new URLSearchParams({ limit: String(limit) });
  if (cursor) parameters.set("cursor", cursor);
  return `/api/superadmin/control-plane/${resource}?${parameters.toString()}`;
};

export async function getPlatformTenantsPage(
  cursor?: string,
  signal?: AbortSignal,
): Promise<PlatformAdminPage<PlatformTenant>> {
  if (cursor && !SAFE_ID.test(cursor)) {
    throw new Error("Некорректный cursor клиентов.");
  }
  return parsePage(
    await platformAdminRequest(pagePath("tenants", 100, cursor), { signal }),
    parseTenant,
  );
}

export async function getPlatformUsersPage(
  cursor?: string,
  signal?: AbortSignal,
): Promise<PlatformAdminPage<PlatformUser>> {
  if (cursor && !SAFE_ID.test(cursor)) {
    throw new Error("Некорректный cursor пользователей.");
  }
  return parsePage(
    await platformAdminRequest(pagePath("users", 100, cursor), { signal }),
    parseUser,
  );
}

export async function getPlatformAuditPage(
  cursor?: string,
  signal?: AbortSignal,
): Promise<PlatformAdminPage<PlatformAuditEvent>> {
  if (cursor && !SAFE_AUDIT_CURSOR.test(cursor)) {
    throw new Error("Некорректный cursor аудита.");
  }
  return parsePage(
    await platformAdminRequest(pagePath("audit", 50, cursor), { signal }),
    parseAuditEvent,
    { maximum: 192, pattern: SAFE_AUDIT_CURSOR },
  );
}

export async function getPlatformAdminSnapshot(signal?: AbortSignal) {
  const [tenants, users, audit] = await Promise.all([
    getPlatformTenantsPage(undefined, signal),
    getPlatformUsersPage(undefined, signal),
    getPlatformAuditPage(undefined, signal),
  ]);
  return {
    tenants: tenants.items,
    users: users.items,
    audit: audit.items,
    tenantCursor: tenants.nextCursor,
    userCursor: users.nextCursor,
    auditCursor: audit.nextCursor,
  };
}

export async function updatePlatformTenant(
  tenantId: string,
  update: TenantPolicyUpdate,
) {
  if (!SAFE_ID.test(tenantId)) throw new Error("Некорректный tenant ID.");
  const value = await platformAdminRequest(
    `/api/superadmin/control-plane/tenants/${encodeURIComponent(tenantId)}`,
    { method: "PATCH", body: JSON.stringify(update) },
  );
  const tenant = parseTenant(value);
  if (!tenant) throw new Error("Backend вернул некорректную политику.");
  return tenant;
}

export async function updatePlatformUser(
  userId: string,
  update: UserControlUpdate,
) {
  if (!SAFE_ID.test(userId)) throw new Error("Некорректный user ID.");
  const value = await platformAdminRequest(
    `/api/superadmin/control-plane/users/${encodeURIComponent(userId)}`,
    { method: "PATCH", body: JSON.stringify(update) },
  );
  const user = parseUser(value);
  if (!user) throw new Error("Backend вернул некорректные настройки.");
  return user;
}

export async function revokePlatformUserSessions(userId: string) {
  if (!SAFE_ID.test(userId)) throw new Error("Некорректный user ID.");
  const value = await platformAdminRequest(
    `/api/superadmin/control-plane/users/${encodeURIComponent(userId)}/sessions`,
    { method: "POST", body: "{}" },
  );
  if (
    !isRecord(value) ||
    value.userId !== userId ||
    integer(value.revokedSessionCount, 0, 1_000_000) === null
  ) {
    throw new Error("Backend вернул некорректный результат отзыва.");
  }
  return value.revokedSessionCount as number;
}

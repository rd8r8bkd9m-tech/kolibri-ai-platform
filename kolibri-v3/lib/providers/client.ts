"use client";

import { withCsrfHeader } from "@/lib/csrf";

export const PROVIDER_IDS = ["mimo-code", "codex-cli"] as const;
export type ProviderId = (typeof PROVIDER_IDS)[number];
export type ProviderStatus =
  | "not_configured"
  | "pending"
  | "connected"
  | "error";

export type ProviderProjection = {
  id: ProviderId;
  displayName: string;
  status: ProviderStatus;
  statusLabel: string;
  authFlowSupported: boolean;
  detail: string;
  lastVerifiedAt: string | null;
};

export type ProviderList = {
  providers: ProviderProjection[];
  authorityConfigured: boolean;
};

export type ProviderEnrollment = {
  provider: ProviderProjection;
};

/**
 * The credential and CLI-login routes are loopback development conveniences.
 * Production always starts a durable, server-owned enrollment intent.
 */
export const LOCAL_PROVIDER_CONNECTIONS_ENABLED =
  process.env.NODE_ENV === "development";

const PROVIDER_PRESENTATION: Record<
  ProviderId,
  {
    displayName: string;
    defaultDetail: string;
  }
> = {
  "mimo-code": {
    displayName: "MiMo Code",
    defaultDetail:
      "Подключение не настроено на стороне Provider Execution Authority.",
  },
  "codex-cli": {
    displayName: "Codex CLI",
    defaultDetail:
      "Подключение не настроено на стороне Provider Execution Authority.",
  },
};

const STATUS_LABELS: Record<ProviderStatus, string> = {
  not_configured: "Не подключён",
  pending: "Ожидает подтверждения",
  connected: "Подключён",
  error: "Требует внимания",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isProviderId(value: unknown): value is ProviderId {
  return (
    typeof value === "string" &&
    (PROVIDER_IDS as readonly string[]).includes(value)
  );
}

function isProviderStatus(value: unknown): value is ProviderStatus {
  return (
    value === "not_configured" ||
    value === "pending" ||
    value === "connected" ||
    value === "error"
  );
}

function safeTimestamp(value: unknown) {
  if (typeof value !== "string" || value.length > 64) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function safeText(value: unknown, fallback: string, maxLength = 500) {
  if (typeof value !== "string") return fallback;
  const candidate = value.trim();
  return candidate.length > 0 && candidate.length <= maxLength
    ? candidate
    : fallback;
}

function defaultProvider(id: ProviderId): ProviderProjection {
  return {
    id,
    displayName: PROVIDER_PRESENTATION[id].displayName,
    status: "not_configured",
    statusLabel: STATUS_LABELS.not_configured,
    authFlowSupported: false,
    detail: PROVIDER_PRESENTATION[id].defaultDetail,
    lastVerifiedAt: null,
  };
}

export function sanitizeProviderProjection(
  value: unknown,
): ProviderProjection | null {
  if (
    !isRecord(value) ||
    !isProviderId(value.id) ||
    !isProviderStatus(value.status)
  ) {
    return null;
  }

  return {
    id: value.id,
    displayName: PROVIDER_PRESENTATION[value.id].displayName,
    status: value.status,
    statusLabel: safeText(
      value.statusLabel,
      STATUS_LABELS[value.status],
      80,
    ),
    authFlowSupported: value.authFlowSupported === true,
    detail: safeText(
      value.detail,
      PROVIDER_PRESENTATION[value.id].defaultDetail,
    ),
    lastVerifiedAt: safeTimestamp(value.lastVerifiedAt),
  };
}

export function sanitizeProviderList(value: unknown): ProviderList | null {
  if (
    !isRecord(value) ||
    !Array.isArray(value.providers) ||
    typeof value.authorityConfigured !== "boolean"
  ) {
    return null;
  }

  const byId = new Map<ProviderId, ProviderProjection>();
  for (const raw of value.providers) {
    const provider = sanitizeProviderProjection(raw);
    if (provider && !byId.has(provider.id)) byId.set(provider.id, provider);
  }

  return {
    providers: PROVIDER_IDS.map(
      (id) => byId.get(id) ?? defaultProvider(id),
    ),
    authorityConfigured: value.authorityConfigured,
  };
}

function sanitizeProviderEnrollment(
  value: unknown,
  providerId: ProviderId,
): ProviderEnrollment | null {
  if (!isRecord(value)) return null;
  const provider = sanitizeProviderProjection(value.provider);
  if (!provider || provider.id !== providerId) return null;
  return { provider };
}

async function request(
  pathname: string,
  init?: RequestInit,
  allowSessionRefresh = true,
): Promise<unknown> {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers = new Headers({
    Accept: "application/json",
    ...init?.headers,
  });
  const protectedHeaders =
    method === "GET" || method === "HEAD"
      ? headers
      : withCsrfHeader(headers);

  const response = await fetch(pathname, {
    ...init,
    headers: protectedHeaders,
    credentials: "same-origin",
    cache: "no-store",
  });
  let payload: unknown = null;
  try {
    payload = (await response.json()) as unknown;
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const errorCode =
      isRecord(payload) && typeof payload.code === "string"
        ? payload.code
        : isRecord(payload) &&
            isRecord(payload.detail) &&
            typeof payload.detail.code === "string"
          ? payload.detail.code
          : null;
    if (
      allowSessionRefresh &&
      method !== "GET" &&
      (errorCode === "csrf_token_required" ||
        errorCode === "csrf_token_stale")
    ) {
      const refreshed = await fetch("/api/v3/session", {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (refreshed.ok) {
        return request(pathname, init, false);
      }
    }
    const nestedDetail =
      isRecord(payload) && isRecord(payload.detail) ? payload.detail : null;
    const message =
      isRecord(payload) &&
      (typeof payload.detail === "string" ||
        typeof payload.message === "string")
        ? safeText(
            typeof payload.detail === "string"
              ? payload.detail
              : payload.message,
            "Операция с провайдером не выполнена.",
          )
        : nestedDetail && typeof nestedDetail.message === "string"
          ? safeText(
              nestedDetail.message,
              "Операция с провайдером не выполнена.",
            )
        : "Операция с провайдером не выполнена.";
    throw new Error(message);
  }
  return payload;
}

export async function connectMimo(apiKey: string) {
  if (!LOCAL_PROVIDER_CONNECTIONS_ENABLED) {
    throw new Error(
      "Локальное подключение MiMo доступно только в режиме разработки.",
    );
  }
  const payload = await request(
    "/api/superadmin/provider-connections/mimo-code/credential",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apiKey }),
    },
  );
  const enrollment = sanitizeProviderEnrollment(payload, "mimo-code");
  if (!enrollment) {
    throw new Error("MiMo не подтвердил подключение.");
  }
  return enrollment;
}

export async function connectCodexLogin() {
  if (!LOCAL_PROVIDER_CONNECTIONS_ENABLED) {
    throw new Error(
      "Локальная проверка Codex доступна только в режиме разработки.",
    );
  }
  const payload = await request(
    "/api/superadmin/provider-connections/codex-cli/login-status",
    { method: "POST" },
  );
  const enrollment = sanitizeProviderEnrollment(payload, "codex-cli");
  if (!enrollment) {
    throw new Error("Codex CLI не подтвердил вход.");
  }
  return enrollment;
}

export function createProviderEnrollmentNonce() {
  return globalThis.crypto.randomUUID();
}

export async function getProviders(signal?: AbortSignal) {
  const payload = await request("/api/superadmin/provider-connections", {
    signal,
  });
  const list = sanitizeProviderList(payload);
  if (!list) {
    throw new Error("Контур провайдеров вернул некорректное состояние.");
  }
  return list;
}

/**
 * Starts a server-owned enrollment. The browser intentionally sends no JSON
 * request payload; provider secrets must never cross the Product/Home BFF
 * boundary.
 */
export async function startProviderEnrollment(
  providerId: ProviderId,
  idempotencyNonce: string,
) {
  const payload = await request(
    `/api/superadmin/provider-connections/${providerId}/enrollments`,
    {
      method: "POST",
      headers: {
        "Idempotency-Key": idempotencyNonce,
      },
    },
  );
  const enrollment = sanitizeProviderEnrollment(payload, providerId);
  if (!enrollment) {
    throw new Error("Контур провайдеров не подтвердил запуск авторизации.");
  }
  return enrollment;
}

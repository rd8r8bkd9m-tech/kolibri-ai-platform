import {
  sanitizeAccountSession,
  sanitizeAccountUser,
  type AccountSession,
  type AccountUser,
  type AgentProfile,
} from "@/lib/identity/contracts";
import { withCsrfHeader } from "@/lib/csrf";

export class AccountApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "AccountApiError";
    this.status = status;
    this.code = code;
  }
}

function safeErrorMessage(value: unknown) {
  const candidate =
    typeof value === "object" &&
    value !== null &&
    "detail" in value &&
    typeof value.detail === "object" &&
    value.detail !== null
      ? value.detail
      : value;
  if (
    typeof candidate === "object" &&
    candidate !== null &&
    "message" in candidate &&
    typeof candidate.message === "string" &&
    candidate.message.trim().length > 0 &&
    candidate.message.length <= 500
  ) {
    return candidate.message.trim();
  }
  return "Не удалось выполнить запрос.";
}

function safeErrorCode(value: unknown, fallback: string) {
  const candidate =
    typeof value === "object" &&
    value !== null &&
    "detail" in value &&
    typeof value.detail === "object" &&
    value.detail !== null
      ? value.detail
      : value;
  return typeof candidate === "object" &&
    candidate !== null &&
    "code" in candidate &&
    typeof candidate.code === "string" &&
    candidate.code.length <= 120
    ? candidate.code
    : fallback;
}

async function requestJson(
  pathname: string,
  init?: RequestInit,
): Promise<unknown> {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers = new Headers({
    Accept: "application/json",
    ...(init?.body ? { "Content-Type": "application/json" } : {}),
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
  if (response.status !== 204) {
    try {
      payload = (await response.json()) as unknown;
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    throw new AccountApiError(
      response.status,
      safeErrorCode(payload, `http_${response.status}`),
      safeErrorMessage(payload),
    );
  }

  return payload;
}

export async function getAccountSession(
  signal?: AbortSignal,
): Promise<AccountSession> {
  const payload = await requestJson("/api/v3/session", { signal });
  const session = sanitizeAccountSession(payload);
  if (!session) {
    throw new AccountApiError(
      502,
      "invalid_session_contract",
      "Backend вернул некорректную сессию.",
    );
  }
  return session;
}

export async function loginAccount(input: {
  email: string;
  password: string;
}) {
  const payload = await requestJson("/api/v3/auth/login", {
    method: "POST",
    body: JSON.stringify(input),
  });
  const session = sanitizeAccountSession(payload);
  if (!session?.authenticated) {
    throw new AccountApiError(
      502,
      "invalid_login_contract",
      "Не удалось подтвердить вход.",
    );
  }
  return session;
}

export async function registerAccount(input: {
  email: string;
  name: string;
  password: string;
}) {
  const payload = await requestJson("/api/v3/auth/register", {
    method: "POST",
    body: JSON.stringify(input),
  });
  const session = sanitizeAccountSession(payload);
  if (!session?.authenticated) {
    throw new AccountApiError(
      502,
      "invalid_registration_contract",
      "Не удалось создать аккаунт.",
    );
  }
  return session;
}

export async function logoutAccount() {
  await requestJson("/api/v3/auth/logout", {
    method: "POST",
  });
}

export async function updateAccountProfile(input: {
  name?: string;
}) {
  const payload = await requestJson("/api/v3/profile", {
    method: "PATCH",
    body: JSON.stringify(input),
  });
  const user = sanitizeAccountUser(payload);
  if (!user) {
    throw new AccountApiError(
      502,
      "invalid_profile_contract",
      "Backend вернул некорректный профиль.",
    );
  }
  return user;
}

export async function updateAgentProfile(profile: AgentProfile) {
  const payload = await requestJson("/api/v3/profile/agent-profile", {
    method: "PUT",
    body: JSON.stringify({ profile }),
  });
  const user = sanitizeAccountUser(payload);
  if (!user) {
    throw new AccountApiError(
      502,
      "invalid_profile_contract",
      "Backend вернул некорректный профиль.",
    );
  }
  return user;
}

export async function updateModelSettings(input: {
  profile: AgentProfile;
  model: string | null;
  reasoningEffort: string | null;
  serviceTier: string | null;
}) {
  const payload = await requestJson("/api/v3/profile/model-settings", {
    method: "PUT",
    body: JSON.stringify(input),
  });
  const user = sanitizeAccountUser(payload);
  if (!user) {
    throw new AccountApiError(
      502,
      "invalid_profile_contract",
      "Backend вернул некорректные настройки модели.",
    );
  }
  return user;
}

export type { AccountSession, AccountUser, AgentProfile };

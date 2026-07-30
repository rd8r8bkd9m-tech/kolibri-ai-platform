import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";

export const API_BASE_URL = "";

export type MobileUser = {
  id: string;
  tenantId: string;
  email: string;
  name: string;
  role: "user" | "owner";
  isPlatformOwner: boolean;
  capabilities: readonly string[];
  entitlements: readonly string[];
  preferredAgentProfile: string;
  preferredModelProfile: string | null;
  preferredModel: string | null;
  preferredReasoningEffort: string | null;
  preferredServiceTier: string | null;
};

type SessionStatus = "restoring" | "signed-out" | "authenticated";
type SessionView = {
  authenticated: boolean;
  user: MobileUser | null;
};
type MobileSessionValue = {
  status: SessionStatus;
  user: MobileUser | null;
  error: string | null;
  login: (input: { email: string; password: string }) => Promise<void>;
  register: (input: {
    email: string;
    name: string;
    password: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
  updateProfile: (input: { name: string }) => Promise<void>;
  updateAgentProfile: (profile: string) => Promise<void>;
  authorizedFetch: typeof fetch;
};

export class MobileApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "MobileApiError";
    this.status = status;
    this.code = code;
  }
}

const MobileSessionContext = createContext<MobileSessionValue | null>(null);
const CSRF_COOKIE = "kolibri_v3_csrf";

const csrfToken = () => {
  const prefix = `${CSRF_COOKIE}=`;
  for (const segment of document.cookie.split(";")) {
    const candidate = segment.trim();
    if (candidate.startsWith(prefix)) {
      return decodeURIComponent(candidate.slice(prefix.length));
    }
  }
  return null;
};

const request = async (path: string, init: RequestInit = {}) => {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (method !== "GET" && method !== "HEAD") {
    const token = csrfToken();
    if (token) headers.set("x-csrf-token", token);
  }
  const response = await fetch(path, {
    ...init,
    cache: "no-store",
    credentials: "same-origin",
    headers,
  });
  if (!response.ok) {
    let code = `http_${response.status}`;
    let message = "Не удалось выполнить запрос.";
    try {
      const payload = (await response.clone().json()) as {
        code?: unknown;
        message?: unknown;
      };
      if (typeof payload.code === "string") code = payload.code;
      if (typeof payload.message === "string") message = payload.message;
    } catch {
      // Raw upstream bodies are never surfaced.
    }
    throw new MobileApiError(response.status, code, message);
  }
  return response;
};

const isStringArray = (value: unknown) =>
  Array.isArray(value) &&
  value.length <= 32 &&
  value.every((item) => typeof item === "string" && item.length <= 96);
const isNullableString = (value: unknown) =>
  value === null || typeof value === "string";

const isMobileUser = (value: unknown): value is MobileUser =>
  typeof value === "object" &&
  value !== null &&
  "id" in value &&
  typeof value.id === "string" &&
  "tenantId" in value &&
  typeof value.tenantId === "string" &&
  "email" in value &&
  typeof value.email === "string" &&
  "name" in value &&
  typeof value.name === "string" &&
  "role" in value &&
  (value.role === "user" || value.role === "owner") &&
  "isPlatformOwner" in value &&
  typeof value.isPlatformOwner === "boolean" &&
  "capabilities" in value &&
  isStringArray(value.capabilities) &&
  "entitlements" in value &&
  isStringArray(value.entitlements) &&
  "preferredAgentProfile" in value &&
  typeof value.preferredAgentProfile === "string" &&
  "preferredModelProfile" in value &&
  isNullableString(value.preferredModelProfile) &&
  "preferredModel" in value &&
  isNullableString(value.preferredModel) &&
  "preferredReasoningEffort" in value &&
  isNullableString(value.preferredReasoningEffort) &&
  "preferredServiceTier" in value &&
  isNullableString(value.preferredServiceTier);

const sessionFrom = async (response: Response) => {
  const value = (await response.json()) as unknown;
  if (
    typeof value !== "object" ||
    value === null ||
    !("authenticated" in value) ||
    typeof value.authenticated !== "boolean" ||
    !("user" in value) ||
    (value.authenticated
      ? !isMobileUser(value.user)
      : value.user !== null)
  ) {
    throw new MobileApiError(
      502,
      "web_session_contract_invalid",
      "Сервер вернул несовместимую сессию.",
    );
  }
  return value as SessionView;
};

const userFrom = async (response: Response) => {
  const value = (await response.json()) as unknown;
  if (!isMobileUser(value)) {
    throw new MobileApiError(
      502,
      "web_profile_contract_invalid",
      "Сервер вернул несовместимый профиль.",
    );
  }
  return value;
};

export function MobileSessionProvider({ children }: PropsWithChildren) {
  const [status, setStatus] = useState<SessionStatus>("restoring");
  const [user, setUser] = useState<MobileUser | null>(null);
  const [error, setError] = useState<string | null>(null);

  const applySession = useCallback((session: SessionView) => {
    setUser(session.user);
    setStatus(session.authenticated ? "authenticated" : "signed-out");
    setError(null);
  }, []);

  useEffect(() => {
    let active = true;
    void request("/api/v3/session")
      .then(sessionFrom)
      .then((session) => {
        if (active) applySession(session);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setUser(null);
        setStatus("signed-out");
        setError(reason instanceof Error ? reason.message : null);
      });
    return () => {
      active = false;
    };
  }, [applySession]);

  const login = useCallback(
    async (input: { email: string; password: string }) => {
      setError(null);
      try {
        applySession(
          await sessionFrom(
            await request("/api/v3/auth/login", {
              method: "POST",
              body: JSON.stringify(input),
            }),
          ),
        );
      } catch (reason) {
        const message =
          reason instanceof MobileApiError &&
          reason.code === "invalid_request"
            ? "Проверьте формат электронной почты и пароля."
            : reason instanceof Error
              ? reason.message
              : "Не удалось войти.";
        setError(message);
        throw reason;
      }
    },
    [applySession],
  );

  const register = useCallback(
    async (input: { email: string; name: string; password: string }) => {
      setError(null);
      try {
        applySession(
          await sessionFrom(
            await request("/api/v3/auth/register", {
              method: "POST",
              body: JSON.stringify(input),
            }),
          ),
        );
      } catch (reason) {
        setError(
          reason instanceof Error ? reason.message : "Не удалось создать аккаунт.",
        );
        throw reason;
      }
    },
    [applySession],
  );

  const logout = useCallback(async () => {
    await request("/api/v3/auth/logout", { method: "POST" });
    applySession({ authenticated: false, user: null });
  }, [applySession]);

  const updateProfile = useCallback(async (input: { name: string }) => {
    setError(null);
    try {
      setUser(
        await userFrom(
          await request("/api/v3/profile", {
            method: "PATCH",
            body: JSON.stringify(input),
          }),
        ),
      );
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Не удалось сохранить профиль.",
      );
      throw reason;
    }
  }, []);

  const updateAgentProfile = useCallback(async (profile: string) => {
    setError(null);
    try {
      setUser(
        await userFrom(
          await request("/api/v3/profile/agent-profile", {
            method: "PUT",
            body: JSON.stringify({ profile }),
          }),
        ),
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Не удалось переключить профиль агента.",
      );
      throw reason;
    }
  }, []);

  const authorizedFetch = useCallback<typeof fetch>(
    (input, init = {}) => {
      const path =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.toString()
            : input.url;
      return request(path, init);
    },
    [],
  );

  const value = useMemo<MobileSessionValue>(
    () => ({
      status,
      user,
      error,
      login,
      register,
      logout,
      updateProfile,
      updateAgentProfile,
      authorizedFetch,
    }),
    [
      authorizedFetch,
      error,
      login,
      logout,
      register,
      status,
      updateAgentProfile,
      updateProfile,
      user,
    ],
  );

  return (
    <MobileSessionContext.Provider value={value}>
      {children}
    </MobileSessionContext.Provider>
  );
}

export function useMobileSession() {
  const value = useContext(MobileSessionContext);
  if (!value) {
    throw new Error(
      "useMobileSession must be used inside MobileSessionProvider.",
    );
  }
  return value;
}

import Constants from "expo-constants";
import { fetch as expoFetch } from "expo/fetch";
import * as SecureStore from "expo-secure-store";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PropsWithChildren,
} from "react";
import { Platform } from "react-native";

const REFRESH_TOKEN_KEY = "kolibri.mobile.refresh-token.v1";
const rawApiBase =
  process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://kolibriai.ru";
const parsedApiBase = new URL(rawApiBase);

if (parsedApiBase.protocol !== "https:") {
  throw new Error("EXPO_PUBLIC_API_BASE_URL must be an absolute HTTPS URL.");
}

export const API_BASE_URL = parsedApiBase.toString().replace(/\/$/, "");
const nativeFetch = expoFetch as unknown as typeof globalThis.fetch;

export type MobileUser = {
  id: string;
  tenantId: string;
  email: string;
  name: string;
  role: "user" | "owner";
  isPlatformOwner: boolean;
  capabilities: readonly string[];
  /**
   * Server-owned grants projected for this exact tenant/user session.
   */
  entitlements: readonly string[];
  preferredAgentProfile: string;
  preferredModelProfile: string | null;
  preferredModel: string | null;
  preferredReasoningEffort: string | null;
  preferredServiceTier: string | null;
};

type TokenPayload = {
  tokenType: "Bearer";
  accessToken: string;
  accessExpiresAt: string;
  refreshToken: string;
  refreshExpiresAt: string;
  deviceSessionId: string;
  user: MobileUser;
};

type SessionStatus = "restoring" | "signed-out" | "authenticated";

type AuthInput = {
  email: string;
  password: string;
};

type RegisterInput = AuthInput & {
  name: string;
};

type MobileSessionValue = {
  status: SessionStatus;
  user: MobileUser | null;
  error: string | null;
  login: (input: AuthInput) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => Promise<void>;
  authorizedFetch: typeof fetch;
};

type ApiErrorShape = {
  code?: unknown;
  message?: unknown;
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

const device = {
  platform: Platform.OS === "android" ? ("android" as const) : ("ios" as const),
  deviceName: Platform.OS === "android" ? "Android device" : "iPhone",
  appVersion: Constants.expoConfig?.version ?? "1.0.0",
};

const readError = async (response: Response) => {
  let shape: ApiErrorShape = {};
  try {
    const payload = (await response.clone().json()) as {
      detail?: ApiErrorShape;
    } & ApiErrorShape;
    shape =
      payload.detail && typeof payload.detail === "object"
        ? payload.detail
        : payload;
  } catch {
    // Do not expose raw server bodies.
  }
  return new MobileApiError(
    response.status,
    typeof shape.code === "string" ? shape.code : `http_${response.status}`,
    typeof shape.message === "string"
      ? shape.message
      : "Не удалось выполнить запрос.",
  );
};

const parseTokenPayload = (value: unknown): TokenPayload => {
  if (
    typeof value !== "object" ||
    value === null ||
    !("tokenType" in value) ||
    value.tokenType !== "Bearer" ||
    !("accessToken" in value) ||
    typeof value.accessToken !== "string" ||
    !("refreshToken" in value) ||
    typeof value.refreshToken !== "string" ||
    !("accessExpiresAt" in value) ||
    typeof value.accessExpiresAt !== "string" ||
    !("refreshExpiresAt" in value) ||
    typeof value.refreshExpiresAt !== "string" ||
    !("deviceSessionId" in value) ||
    typeof value.deviceSessionId !== "string" ||
    !("user" in value) ||
    typeof value.user !== "object" ||
    value.user === null ||
    !("capabilities" in value.user) ||
    !Array.isArray(value.user.capabilities) ||
    value.user.capabilities.length > 32 ||
    value.user.capabilities.some(
      (claim) =>
        typeof claim !== "string" ||
        !/^[a-z][a-z0-9._-]{1,95}$/.test(claim),
    ) ||
    new Set(value.user.capabilities).size !== value.user.capabilities.length ||
    !("entitlements" in value.user) ||
    !Array.isArray(value.user.entitlements) ||
    value.user.entitlements.length > 32 ||
    value.user.entitlements.some(
      (claim) =>
        typeof claim !== "string" ||
        !/^[a-z][a-z0-9._-]{1,95}$/.test(claim),
    ) ||
    new Set(value.user.entitlements).size !== value.user.entitlements.length
  ) {
    throw new MobileApiError(
      502,
      "mobile_auth_contract_invalid",
      "Сервер вернул несовместимую сессию.",
    );
  }
  return value as TokenPayload;
};

const publicRequest = async (path: string, body: unknown) => {
  const response = await nativeFetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await readError(response);
  return parseTokenPayload(await response.json());
};

export function MobileSessionProvider({ children }: PropsWithChildren) {
  const [status, setStatus] = useState<SessionStatus>("restoring");
  const [user, setUser] = useState<MobileUser | null>(null);
  const [error, setError] = useState<string | null>(null);
  const accessTokenRef = useRef<string | null>(null);
  const refreshTokenRef = useRef<string | null>(null);
  const refreshPromiseRef = useRef<Promise<string> | null>(null);

  const clearSession = useCallback(async () => {
    accessTokenRef.current = null;
    refreshTokenRef.current = null;
    setUser(null);
    setStatus("signed-out");
    await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
  }, []);

  const commitPair = useCallback(async (pair: TokenPayload) => {
    await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, pair.refreshToken, {
      keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    });
    accessTokenRef.current = pair.accessToken;
    refreshTokenRef.current = pair.refreshToken;
    setUser(pair.user);
    setError(null);
    setStatus("authenticated");
    return pair.accessToken;
  }, []);

  const rotate = useCallback(async () => {
    if (refreshPromiseRef.current) return refreshPromiseRef.current;

    const operation = (async () => {
      const refreshToken =
        refreshTokenRef.current ??
        (await SecureStore.getItemAsync(REFRESH_TOKEN_KEY));
      if (!refreshToken) {
        await clearSession();
        throw new MobileApiError(
          401,
          "mobile_refresh_token_invalid",
          "Войдите в аккаунт.",
        );
      }
      refreshTokenRef.current = refreshToken;
      try {
        return await commitPair(
          await publicRequest("/v1/mobile/auth/refresh", { refreshToken }),
        );
      } catch (reason) {
        const authFailure =
          reason instanceof MobileApiError &&
          (reason.code === "mobile_refresh_token_invalid" ||
            reason.code === "mobile_refresh_token_reused");
        if (authFailure) await clearSession();
        throw reason;
      }
    })().finally(() => {
      refreshPromiseRef.current = null;
    });

    refreshPromiseRef.current = operation;
    return operation;
  }, [clearSession, commitPair]);

  useEffect(() => {
    let active = true;
    rotate().catch((reason: unknown) => {
      if (!active) return;
      setError(
        reason instanceof MobileApiError &&
          reason.code !== "mobile_refresh_token_invalid"
          ? reason.message
          : null,
      );
      setStatus("signed-out");
    });
    return () => {
      active = false;
    };
  }, [rotate]);

  const establish = useCallback(
    async (path: "/v1/mobile/auth/login" | "/v1/mobile/auth/register", body: unknown) => {
      setError(null);
      try {
        await commitPair(await publicRequest(path, body));
      } catch (reason) {
        const message =
          reason instanceof Error ? reason.message : "Не удалось войти.";
        setError(message);
        throw reason;
      }
    },
    [commitPair],
  );

  const login = useCallback(
    (input: AuthInput) =>
      establish("/v1/mobile/auth/login", { ...input, device }),
    [establish],
  );

  const register = useCallback(
    (input: RegisterInput) =>
      establish("/v1/mobile/auth/register", { ...input, device }),
    [establish],
  );

  const logout = useCallback(async () => {
    const refreshToken =
      refreshTokenRef.current ??
      (await SecureStore.getItemAsync(REFRESH_TOKEN_KEY));
    try {
      if (refreshToken) {
        await nativeFetch(`${API_BASE_URL}/v1/mobile/auth/logout`, {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ refreshToken }),
        });
      }
    } finally {
      await clearSession();
    }
  }, [clearSession]);

  const authorizedFetch = useCallback<typeof fetch>(
    async (input, init = {}) => {
      const execute = async (token: string) => {
        const headers = new Headers(init.headers);
        headers.set("Authorization", `Bearer ${token}`);
        return nativeFetch(input, { ...init, headers });
      };

      const current = accessTokenRef.current ?? (await rotate());
      const response = await execute(current);
      if (response.status !== 401) return response;

      const refreshed =
        accessTokenRef.current && accessTokenRef.current !== current
          ? accessTokenRef.current
          : await rotate();
      const retry = await execute(refreshed);
      if (retry.status === 401) {
        await clearSession();
      }
      return retry;
    },
    [clearSession, rotate],
  );

  const value = useMemo<MobileSessionValue>(
    () => ({
      status,
      user,
      error,
      login,
      register,
      logout,
      authorizedFetch,
    }),
    [authorizedFetch, error, login, logout, register, status, user],
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
    throw new Error("useMobileSession must be used inside MobileSessionProvider");
  }
  return value;
}

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
const REFRESH_TOKEN_LOCK = "kolibri.mobile.refresh-token-rotation.v1";
const rawApiBase =
	process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://kolibriai.ru";
const parsedApiBase = new URL(rawApiBase);

// Expo Web normally reports `Platform.OS === "web"`. Keep the browser
// runtime check as a second guard because a stale/native-compatible bundle can
// otherwise load expo-secure-store and call its native bridge on the Web.
// Refresh tokens remain in the browser's origin-scoped storage in that case;
// native platforms continue to use the OS keychain below.
const isWebRuntime =
	Platform.OS === "web" || typeof globalThis.window !== "undefined";

const isLoopbackHost = (hostname: string) => {
	const normalized = hostname.toLowerCase().replace(/^\[(.*)\]$/, "$1");
	return (
		normalized === "localhost" ||
		normalized === "::1" ||
		normalized === "127.0.0.1" ||
		/^127(?:\.\d{1,3}){3}$/.test(normalized)
	);
};

const localWebDevelopment =
	isWebRuntime &&
	process.env.NODE_ENV !== "production" &&
	isLoopbackHost(parsedApiBase.hostname);

if (
	parsedApiBase.protocol !== "https:" &&
	!(parsedApiBase.protocol === "http:" && localWebDevelopment)
) {
	throw new Error(
		"EXPO_PUBLIC_API_BASE_URL must be HTTPS (HTTP is allowed only for local Expo web development).",
	);
}

export const API_BASE_URL = parsedApiBase.toString().replace(/\/$/, "");
const nativeFetch = expoFetch as unknown as typeof globalThis.fetch;

const browserRefreshTokenStorage = {
	get(): string | null {
		if (!isWebRuntime) return null;
		try {
			return globalThis.localStorage.getItem(REFRESH_TOKEN_KEY);
		} catch {
			return null;
		}
	},
	set(value: string) {
		if (!isWebRuntime) return;
		try {
			globalThis.localStorage.setItem(REFRESH_TOKEN_KEY, value);
		} catch {
			// Private browsing may reject persistent storage; the in-memory access
			// token still keeps the current session usable until a reload.
		}
	},
	clear() {
		if (!isWebRuntime) return;
		try {
			globalThis.localStorage.removeItem(REFRESH_TOKEN_KEY);
		} catch {
			// Nothing to clear when browser storage is unavailable.
		}
	},
};

const getRefreshToken = async () =>
	isWebRuntime
		? browserRefreshTokenStorage.get()
		: await SecureStore.getItemAsync(REFRESH_TOKEN_KEY);

const setRefreshToken = async (value: string) => {
	if (isWebRuntime) {
		browserRefreshTokenStorage.set(value);
		return;
	}
	await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, value, {
		keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
	});
};

const clearRefreshToken = async () => {
	if (isWebRuntime) {
		browserRefreshTokenStorage.clear();
		return;
	}
	await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
};

const withRefreshTokenLock = async <T,>(operation: () => Promise<T>) => {
	if (!isWebRuntime) return operation();
	const locks = (
		globalThis as typeof globalThis & {
			navigator?: {
				locks?: {
					request: <Result>(
						name: string,
						callback: () => Promise<Result>,
					) => Promise<Result>;
				};
			};
	}
	).navigator?.locks;
	return locks ? locks.request(REFRESH_TOKEN_LOCK, operation) : operation();
};

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
	refreshProfile: () => Promise<MobileUser>;
	updateProfile: (input: { name: string }) => Promise<MobileUser>;
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

const PROFILE_ID = /^[a-z0-9][a-z0-9._-]{1,95}$/;
const MODEL_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/;
const REASONING_EFFORT = /^[a-z0-9][a-z0-9_-]{0,31}$/;
const SERVICE_TIER = /^[a-z0-9][a-z0-9_-]{0,31}$/;
const CLAIM_ID = /^[a-z][a-z0-9._-]{1,95}$/;

const optionalSetting = (value: unknown, pattern: RegExp) => {
	if (value === null || value === undefined) return null;
	return typeof value === "string" && pattern.test(value) ? value : undefined;
};

const parseMobileUser = (value: unknown): MobileUser => {
	if (typeof value !== "object" || value === null) {
		throw new MobileApiError(
			502,
			"mobile_auth_contract_invalid",
			"Сервер вернул несовместимый профиль.",
		);
	}
	const user = value as Record<string, unknown>;
	const id = typeof user.id === "string" ? user.id : "";
	const tenantId = typeof user.tenantId === "string" ? user.tenantId : "";
	const email = typeof user.email === "string" ? user.email.trim().toLowerCase() : "";
	const name = typeof user.name === "string" ? user.name.trim() : "";
	const role = user.role;
	const isPlatformOwner = user.isPlatformOwner;
	const capabilities = user.capabilities;
	const entitlements = user.entitlements;
	const preferredAgentProfile = user.preferredAgentProfile;
	const preferredModelProfile = optionalSetting(
		user.preferredModelProfile,
		PROFILE_ID,
	);
	const preferredModel = optionalSetting(user.preferredModel, MODEL_ID);
	const preferredReasoningEffort = optionalSetting(
		user.preferredReasoningEffort,
		REASONING_EFFORT,
	);
	const preferredServiceTier = optionalSetting(
		user.preferredServiceTier,
		SERVICE_TIER,
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
		(role !== "user" && role !== "owner") ||
		typeof isPlatformOwner !== "boolean" ||
		isPlatformOwner !== (role === "owner") ||
		!Array.isArray(capabilities) ||
		capabilities.length > 32 ||
		capabilities.some((claim) => typeof claim !== "string" || !CLAIM_ID.test(claim)) ||
		new Set(capabilities).size !== capabilities.length ||
		!Array.isArray(entitlements) ||
		entitlements.length > 32 ||
		entitlements.some((claim) => typeof claim !== "string" || !CLAIM_ID.test(claim)) ||
		new Set(entitlements).size !== entitlements.length ||
		typeof preferredAgentProfile !== "string" ||
		!PROFILE_ID.test(preferredAgentProfile) ||
		preferredModelProfile === undefined ||
		preferredModel === undefined ||
		preferredReasoningEffort === undefined ||
		preferredServiceTier === undefined
	) {
		throw new MobileApiError(
			502,
			"mobile_auth_contract_invalid",
			"Сервер вернул несовместимый профиль.",
		);
	}

	return {
		id,
		tenantId,
		email,
		name,
		role,
		isPlatformOwner,
		capabilities: capabilities as string[],
		entitlements: entitlements as string[],
		preferredAgentProfile,
		preferredModelProfile,
		preferredModel,
		preferredReasoningEffort,
		preferredServiceTier,
	};
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
		!("user" in value)
	) {
		throw new MobileApiError(
			502,
			"mobile_auth_contract_invalid",
			"Сервер вернул несовместимую сессию.",
		);
	}
	return { ...(value as TokenPayload), user: parseMobileUser(value.user) };
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
		await clearRefreshToken();
	}, []);

	const commitPair = useCallback(async (pair: TokenPayload) => {
		await setRefreshToken(pair.refreshToken);
		accessTokenRef.current = pair.accessToken;
		refreshTokenRef.current = pair.refreshToken;
		setUser(pair.user);
		setError(null);
		setStatus("authenticated");
		return pair.accessToken;
	}, []);

	const rotate = useCallback(async () => {
		if (refreshPromiseRef.current) return refreshPromiseRef.current;

		const operation = withRefreshTokenLock(async () => {
			const refreshToken =
				isWebRuntime
					? await getRefreshToken()
					: refreshTokenRef.current ?? (await getRefreshToken());
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
		}).finally(() => {
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
		async (
			path: "/v1/mobile/auth/login" | "/v1/mobile/auth/register",
			body: unknown,
		) => {
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
			isWebRuntime
				? await getRefreshToken()
				: refreshTokenRef.current ?? (await getRefreshToken());
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

	const refreshProfile = useCallback(async () => {
		const response = await authorizedFetch(
			`${API_BASE_URL}/v1/mobile/auth/session`,
			{ headers: { Accept: "application/json" }, cache: "no-store" },
		);
		if (!response.ok) throw await readError(response);
		let payload: unknown = null;
		try {
			payload = await response.json();
		} catch {
			throw new MobileApiError(
				502,
				"mobile_auth_contract_invalid",
				"Сервер вернул несовместимый профиль.",
			);
		}
		if (typeof payload !== "object" || payload === null || !("user" in payload)) {
			throw new MobileApiError(
				502,
				"mobile_auth_contract_invalid",
				"Сервер вернул несовместимый профиль.",
			);
		}
		const updated = parseMobileUser(payload.user);
		setUser(updated);
		return updated;
	}, [authorizedFetch]);

	const updateProfile = useCallback(
		async ({ name }: { name: string }) => {
			const normalizedName = name.trim();
			if (normalizedName.length < 1 || normalizedName.length > 160) {
				throw new MobileApiError(
					422,
					"profile_name_invalid",
					"Имя должно содержать от 1 до 160 символов.",
				);
			}
			const response = await authorizedFetch(`${API_BASE_URL}/v1/profile`, {
				method: "PATCH",
				headers: {
					Accept: "application/json",
					"Content-Type": "application/json",
				},
				body: JSON.stringify({ name: normalizedName }),
			});
			if (!response.ok) throw await readError(response);
			const updated = parseMobileUser(await response.json());
			setUser(updated);
			return updated;
		},
		[authorizedFetch],
	);

	const value = useMemo<MobileSessionValue>(
		() => ({
			status,
			user,
			error,
			login,
			register,
			refreshProfile,
			updateProfile,
			logout,
			authorizedFetch,
		}),
		[
			authorizedFetch,
			error,
			login,
			logout,
			refreshProfile,
			register,
			status,
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
			"useMobileSession must be used inside MobileSessionProvider",
		);
	}
	return value;
}

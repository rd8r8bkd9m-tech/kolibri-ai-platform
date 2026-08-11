import { API_BASE_URL, MobileApiError } from "@/src/auth/mobile-session";

export type AuthorizedFetch = typeof fetch;

export type BillingPaymentStatus =
	| "initializing"
	| "pending"
	| "unknown"
	| "authorized"
	| "succeeded"
	| "failed"
	| "canceled"
	| "partially_refunded"
	| "refunded";

export type BillingPlan = {
	code: string;
	name: string;
	amountMinor: number;
	currency: "RUB";
	durationSeconds: number;
	entitlement: string;
	revision: number;
};

export type BillingPaymentIntent = {
	id: string;
	planCode: string;
	planName: string;
	amountMinor: number;
	currency: "RUB";
	status: BillingPaymentStatus;
	providerStatus: string | null;
	paymentUrl: string | null;
	createdAt: number;
	updatedAt: number;
};

export type BillingSubscription = {
	id: string;
	planCode: string;
	entitlement: string;
	paymentIntentId: string;
	status: "active" | "refunded" | "canceled" | "expired";
	currentPeriodStart: number;
	currentPeriodEnd: number;
	autoRenew: boolean;
	renewalAttempts: number;
	rebillConfigured: boolean;
};

const PLAN_CODE = /^[a-z0-9][a-z0-9._-]{0,47}$/;
const ENTITLEMENT_CODE = /^[a-z0-9][a-z0-9._-]{2,95}$/;
const PAYMENT_INTENT_ID = /^payment_intent_[0-9a-f]{32}$/;
const PAYMENT_STATUSES = new Set<BillingPaymentStatus>([
	"initializing",
	"pending",
	"unknown",
	"authorized",
	"succeeded",
	"failed",
	"canceled",
	"partially_refunded",
	"refunded",
]);

const isRecord = (value: unknown): value is Record<string, unknown> =>
	typeof value === "object" && value !== null && !Array.isArray(value);

const boundedString = (value: unknown, maximum: number): value is string =>
	typeof value === "string" && value.length > 0 && value.length <= maximum;

const integerBetween = (
	value: unknown,
	minimum: number,
	maximum: number,
): value is number =>
	typeof value === "number" &&
	Number.isSafeInteger(value) &&
	value >= minimum &&
	value <= maximum;

const safePaymentUrl = (value: unknown): value is string | null => {
	if (value === null) return true;
	if (!boundedString(value, 2_048)) return false;
	try {
		const parsed = new URL(value);
		return (
			parsed.protocol === "https:" &&
			!parsed.username &&
			!parsed.password &&
			(parsed.hostname.endsWith(".tinkoff.ru") ||
				parsed.hostname.endsWith(".tbank.ru"))
		);
	} catch {
		return false;
	}
};

const sanitizePlan = (value: unknown): BillingPlan | null => {
	if (
		!isRecord(value) ||
		!boundedString(value.code, 48) ||
		!PLAN_CODE.test(value.code) ||
		!boundedString(value.name, 120) ||
		!integerBetween(value.amountMinor, 1, 9_999_999_999) ||
		value.currency !== "RUB" ||
		!integerBetween(value.durationSeconds, 3_600, 31_622_400) ||
		!boundedString(value.entitlement, 96) ||
		!ENTITLEMENT_CODE.test(value.entitlement) ||
		!integerBetween(value.revision, 1, Number.MAX_SAFE_INTEGER)
	) {
		return null;
	}
	return {
		code: value.code,
		name: value.name,
		amountMinor: value.amountMinor,
		currency: value.currency,
		durationSeconds: value.durationSeconds,
		entitlement: value.entitlement,
		revision: value.revision,
	};
};

const sanitizePayment = (value: unknown): BillingPaymentIntent | null => {
	if (
		!isRecord(value) ||
		!boundedString(value.id, 96) ||
		!PAYMENT_INTENT_ID.test(value.id) ||
		!boundedString(value.planCode, 48) ||
		!PLAN_CODE.test(value.planCode) ||
		!boundedString(value.planName, 120) ||
		!integerBetween(value.amountMinor, 1, 9_999_999_999) ||
		value.currency !== "RUB" ||
		!boundedString(value.status, 32) ||
		!PAYMENT_STATUSES.has(value.status as BillingPaymentStatus) ||
		(value.providerStatus !== null && !boundedString(value.providerStatus, 48)) ||
		!safePaymentUrl(value.paymentUrl) ||
		!integerBetween(value.createdAt, 0, Number.MAX_SAFE_INTEGER) ||
		!integerBetween(value.updatedAt, 0, Number.MAX_SAFE_INTEGER)
	) {
		return null;
	}
	return {
		id: value.id,
		planCode: value.planCode,
		planName: value.planName,
		amountMinor: value.amountMinor,
		currency: value.currency,
		status: value.status as BillingPaymentStatus,
		providerStatus: value.providerStatus as string | null,
		paymentUrl: value.paymentUrl as string | null,
		createdAt: value.createdAt,
		updatedAt: value.updatedAt,
	};
};

const sanitizeSubscription = (value: unknown): BillingSubscription | null => {
	if (
		!isRecord(value) ||
		!boundedString(value.id, 96) ||
		!boundedString(value.planCode, 48) ||
		!PLAN_CODE.test(value.planCode) ||
		!boundedString(value.entitlement, 96) ||
		!ENTITLEMENT_CODE.test(value.entitlement) ||
		!boundedString(value.paymentIntentId, 96) ||
		!PAYMENT_INTENT_ID.test(value.paymentIntentId) ||
		!boundedString(value.status, 24) ||
		!["active", "refunded", "canceled", "expired"].includes(value.status) ||
		!integerBetween(value.currentPeriodStart, 0, Number.MAX_SAFE_INTEGER) ||
		!integerBetween(value.currentPeriodEnd, 1, Number.MAX_SAFE_INTEGER) ||
		value.currentPeriodEnd <= value.currentPeriodStart ||
		typeof value.autoRenew !== "boolean" ||
		!integerBetween(value.renewalAttempts, 0, 999) ||
		typeof value.rebillConfigured !== "boolean"
	) {
		return null;
	}
	return {
		id: value.id,
		planCode: value.planCode,
		entitlement: value.entitlement,
		paymentIntentId: value.paymentIntentId,
		status: value.status as BillingSubscription["status"],
		currentPeriodStart: value.currentPeriodStart,
		currentPeriodEnd: value.currentPeriodEnd,
		autoRenew: value.autoRenew,
		renewalAttempts: value.renewalAttempts,
		rebillConfigured: value.rebillConfigured,
	};
};

const contractError = () =>
	new MobileApiError(
		502,
		"billing_contract_invalid",
		"Сервис оплаты вернул некорректные данные.",
	);

const readError = async (response: Response) => {
	let payload: unknown = null;
	try {
		payload = await response.clone().json();
	} catch {
		// Raw provider/backend bodies are intentionally never shown to the user.
	}
	const candidate =
		isRecord(payload) && isRecord(payload.detail) ? payload.detail : payload;
	const details = isRecord(candidate) ? candidate : null;
	return new MobileApiError(
		response.status,
		boundedString(details?.code, 120)
			? details.code
			: `http_${response.status}`,
		boundedString(details?.message, 500)
			? details.message
			: "Не удалось получить данные оплаты.",
	);
};

const requestJson = async (
	authorizedFetch: AuthorizedFetch,
	pathname: string,
	init: RequestInit = {},
) => {
	const headers = new Headers({ Accept: "application/json", ...init.headers });
	if (init.body) headers.set("Content-Type", "application/json");
	const response = await authorizedFetch(`${API_BASE_URL}${pathname}`, {
		...init,
		headers,
		cache: "no-store",
	});
	if (!response.ok) throw await readError(response);
	try {
		return (await response.json()) as unknown;
	} catch {
		throw contractError();
	}
};

const listItems = <T,>(
	payload: unknown,
	sanitize: (value: unknown) => T | null,
) => {
	if (!isRecord(payload) || !Array.isArray(payload.items) || payload.items.length > 100) {
		throw contractError();
	}
	const items = payload.items.map(sanitize);
	if (items.some((item) => item === null)) throw contractError();
	return items as T[];
};

export async function getWebBillingPlans(
	authorizedFetch: AuthorizedFetch,
	signal?: AbortSignal,
) {
	return listItems(
		await requestJson(authorizedFetch, "/v1/billing/plans", { signal }),
		sanitizePlan,
	);
}

export async function getWebBillingSubscriptions(
	authorizedFetch: AuthorizedFetch,
	signal?: AbortSignal,
) {
	return listItems(
		await requestJson(authorizedFetch, "/v1/billing/subscriptions", { signal }),
		sanitizeSubscription,
	);
}

export async function createWebBillingPayment(
	authorizedFetch: AuthorizedFetch,
	planCode: string,
	idempotencyKey: string,
) {
	if (!PLAN_CODE.test(planCode) || idempotencyKey.length < 16) {
		throw new MobileApiError(422, "billing_request_invalid", "Тариф не выбран.");
	}
	const payment = sanitizePayment(
		await requestJson(authorizedFetch, "/v1/billing/payment-intents", {
			method: "POST",
			headers: { "Idempotency-Key": idempotencyKey },
			body: JSON.stringify({ planCode, returnSurface: "pwa" }),
		}),
	);
	if (!payment) throw contractError();
	return payment;
}

export async function getWebBillingPayment(
	authorizedFetch: AuthorizedFetch,
	intentId: string,
	signal?: AbortSignal,
) {
	if (!PAYMENT_INTENT_ID.test(intentId)) {
		throw new MobileApiError(
			404,
			"billing_payment_not_found",
			"Платёж не найден.",
		);
	}
	const payment = sanitizePayment(
		await requestJson(
			authorizedFetch,
			`/v1/billing/payment-intents/${encodeURIComponent(intentId)}`,
			{ signal },
		),
	);
	if (!payment) throw contractError();
	return payment;
}

export function createWebBillingIdempotencyKey() {
	return `billing-pwa-${globalThis.crypto.randomUUID()}`;
}

export async function setWebBillingAutoRenew(
	authorizedFetch: AuthorizedFetch,
	subscriptionId: string,
	enabled: boolean,
) {
	const payload = await requestJson(
		authorizedFetch,
		`/v1/billing/subscriptions/${encodeURIComponent(subscriptionId)}/auto-renew`,
		{
			method: "POST",
			body: JSON.stringify({ enabled }),
		},
	);
	const subscription = sanitizeSubscription(payload);
	if (!subscription) throw contractError();
	return subscription;
}

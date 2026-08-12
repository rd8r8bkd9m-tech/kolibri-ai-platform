import { withCsrfHeader } from "@/lib/csrf";

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

export type BillingReturnSurface = "web" | "pwa";

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
	paidAt: number | null;
};

/** Read-only history item; the backend intentionally omits paymentUrl. */
export type BillingPaymentRecord = Omit<
	BillingPaymentIntent,
	"paymentUrl"
>;

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
	nextRenewalAt: number;
};

export class BillingApiError extends Error {
	readonly code: string;
	readonly status: number;

	constructor(status: number, code: string, message: string) {
		super(message);
		this.name = "BillingApiError";
		this.status = status;
		this.code = code;
	}
}

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

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function boundedString(value: unknown, maximum: number): value is string {
	return typeof value === "string" && value.length > 0 && value.length <= maximum;
}

function integerBetween(
	value: unknown,
	minimum: number,
	maximum: number,
): value is number {
	return (
		typeof value === "number" &&
		Number.isSafeInteger(value) &&
		value >= minimum &&
		value <= maximum
	);
}

function safePaymentUrl(value: unknown): value is string | null {
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
}

function sanitizePlan(value: unknown): BillingPlan | null {
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
}

function sanitizePayment(value: unknown): BillingPaymentIntent | null {
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
		(value.providerStatus !== null &&
			!boundedString(value.providerStatus, 48)) ||
		!safePaymentUrl(value.paymentUrl) ||
		!integerBetween(value.createdAt, 0, Number.MAX_SAFE_INTEGER) ||
		!integerBetween(value.updatedAt, 0, Number.MAX_SAFE_INTEGER) ||
		(value.paidAt !== null && !integerBetween(value.paidAt, 1, Number.MAX_SAFE_INTEGER))
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
		paidAt:
			typeof value.paidAt === "number"
				? (value.paidAt as number)
				: null,
	};
}

function sanitizeHistoryPayment(value: unknown): BillingPaymentRecord | null {
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
		(value.providerStatus !== null &&
			!boundedString(value.providerStatus, 48)) ||
		"paymentUrl" in value ||
		!integerBetween(value.createdAt, 0, Number.MAX_SAFE_INTEGER) ||
		!integerBetween(value.updatedAt, 0, Number.MAX_SAFE_INTEGER) ||
		(value.paidAt !== null && !integerBetween(value.paidAt, 1, Number.MAX_SAFE_INTEGER))
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
		createdAt: value.createdAt,
		updatedAt: value.updatedAt,
		paidAt:
			typeof value.paidAt === "number"
				? (value.paidAt as number)
				: null,
	};
}

function sanitizeSubscription(value: unknown): BillingSubscription | null {
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
		typeof value.rebillConfigured !== "boolean" ||
		!integerBetween(value.nextRenewalAt, 1, Number.MAX_SAFE_INTEGER)
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
		nextRenewalAt: value.nextRenewalAt,
	};
}

function errorDetails(value: unknown) {
	const candidate =
		isRecord(value) && isRecord(value.detail) ? value.detail : value;
	return isRecord(candidate) ? candidate : null;
}

async function requestJson(
	pathname: string,
	init: RequestInit = {},
): Promise<unknown> {
	const method = (init.method ?? "GET").toUpperCase();
	const headers = new Headers({ Accept: "application/json", ...init.headers });
	if (init.body) headers.set("Content-Type", "application/json");
	const protectedHeaders =
		method === "GET" || method === "HEAD" ? headers : withCsrfHeader(headers);
	const response = await fetch(pathname, {
		...init,
		headers: protectedHeaders,
		credentials: "same-origin",
		cache: "no-store",
	});
	let payload: unknown = null;
	try {
		payload = await response.json();
	} catch {
		payload = null;
	}
	if (!response.ok) {
		const details = errorDetails(payload);
		const code = boundedString(details?.code, 120)
			? details.code
			: `http_${response.status}`;
		const message = boundedString(details?.message, 500)
			? details.message
			: "Не удалось получить данные оплаты.";
		throw new BillingApiError(response.status, code, message);
	}
	return payload;
}

function listItems<T>(
	payload: unknown,
	sanitize: (value: unknown) => T | null,
): T[] {
	if (!isRecord(payload) || !Array.isArray(payload.items) || payload.items.length > 100) {
		throw new BillingApiError(
			502,
			"billing_contract_invalid",
			"Сервис оплаты вернул некорректные данные.",
		);
	}
	const items = payload.items.map(sanitize);
	if (items.some((item) => item === null)) {
		throw new BillingApiError(
			502,
			"billing_contract_invalid",
			"Сервис оплаты вернул некорректные данные.",
		);
	}
	return items as T[];
}

export async function getBillingPlans(signal?: AbortSignal) {
	return listItems(
		await requestJson("/api/v3/billing/plans", { signal }),
		sanitizePlan,
	);
}

export async function getBillingSubscriptions(signal?: AbortSignal) {
	return listItems(
		await requestJson("/api/v3/billing/subscriptions", { signal }),
		sanitizeSubscription,
	);
}

export async function getBillingPayments(signal?: AbortSignal) {
	return listItems(
		await requestJson("/api/v3/billing/payments", { signal }),
		sanitizeHistoryPayment,
	);
}

export async function setBillingAutoRenew(
	subscriptionId: string,
	enabled: boolean,
) {
	const subscription = sanitizeSubscription(
		await requestJson(
			`/api/v3/billing/subscriptions/${encodeURIComponent(subscriptionId)}/auto-renew`,
			{
				method: "POST",
				body: JSON.stringify({ enabled }),
			},
		),
	);
	if (!subscription) {
		throw new BillingApiError(
			502,
			"billing_contract_invalid",
			"Сервис оплаты вернул некорректную подписку.",
		);
	}
	return subscription;
}

export async function createBillingPayment(
	planCode: string,
	idempotencyKey: string,
	returnSurface: BillingReturnSurface = "web",
) {
	if (
		!PLAN_CODE.test(planCode) ||
		idempotencyKey.length < 16 ||
		(returnSurface !== "web" && returnSurface !== "pwa")
	) {
		throw new BillingApiError(422, "billing_request_invalid", "Тариф не выбран.");
	}
	const payment = sanitizePayment(
		await requestJson("/api/v3/billing/payment-intents", {
			method: "POST",
		headers: { "Idempotency-Key": idempotencyKey },
			body: JSON.stringify({ planCode, returnSurface }),
		}),
	);
	if (!payment) {
		throw new BillingApiError(
			502,
			"billing_contract_invalid",
			"Сервис оплаты вернул некорректный платёж.",
		);
	}
	return payment;
}

export async function getBillingPayment(
	intentId: string,
	signal?: AbortSignal,
) {
	if (!PAYMENT_INTENT_ID.test(intentId)) {
		throw new BillingApiError(404, "billing_payment_not_found", "Платёж не найден.");
	}
	const payment = sanitizePayment(
		await requestJson(
			`/api/v3/billing/payment-intents/${encodeURIComponent(intentId)}`,
			{ signal },
		),
	);
	if (!payment) {
		throw new BillingApiError(
			502,
			"billing_contract_invalid",
			"Сервис оплаты вернул некорректный платёж.",
		);
	}
	return payment;
}

export async function refreshBillingPayment(intentId: string) {
	if (!PAYMENT_INTENT_ID.test(intentId)) {
		throw new BillingApiError(404, "billing_payment_not_found", "Платёж не найден.");
	}
	const payment = sanitizePayment(
		await requestJson(
			`/api/v3/billing/payment-intents/${encodeURIComponent(intentId)}/refresh`,
			{ method: "POST" },
		),
	);
	if (!payment) {
		throw new BillingApiError(
			502,
			"billing_contract_invalid",
			"Сервис оплаты вернул некорректный платёж.",
		);
	}
	return payment;
}

export function createBillingIdempotencyKey() {
	return `billing-web-${crypto.randomUUID()}`;
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
	BillingApiError,
	type BillingPaymentIntent,
	type BillingPaymentRecord,
	type BillingPlan,
	type BillingReturnSurface,
	type BillingSubscription,
	createBillingIdempotencyKey,
	createBillingPayment,
	getBillingPayments,
	getBillingPlans,
	getBillingSubscriptions,
	refreshBillingPayment,
	setBillingAutoRenew,
} from "@/lib/billing/client";

const DRAFT_KEY = "kolibri.billing.checkout.v1";
const DRAFT_LIFETIME_MS = 24 * 60 * 60 * 1_000;
const SAFE_PLAN_CODE = /^[a-z0-9][a-z0-9._-]{0,47}$/;
const SAFE_IDEMPOTENCY_KEY = /^[A-Za-z0-9._:-]{16,128}$/;
const SAFE_INTENT_ID = /^payment_intent_[0-9a-f]{32}$/;
const TERMINAL_PAYMENT_STATUSES = new Set([
	"succeeded",
	"failed",
	"canceled",
	"partially_refunded",
	"refunded",
]);

type CheckoutDraft = {
	createdAt: number;
	idempotencyKey: string;
	intentId?: string;
	planCode: string;
	returnSurface: BillingReturnSurface;
};

type BillingAccountOptions = {
	returnSurface?: BillingReturnSurface;
};

function detectReturnSurface(): BillingReturnSurface {
	if (typeof window === "undefined") return "web";
	const url = new URL(window.location.href);
	return url.pathname === "/account" || url.searchParams.get("client") === "mobile"
		? "pwa"
		: "web";
}

function readDraft(): CheckoutDraft | null {
	try {
		const value = JSON.parse(sessionStorage.getItem(DRAFT_KEY) ?? "null");
		const age = Date.now() - Number(value?.createdAt);
		// Drafts created before the PWA return-surface field are still safe to
		// resume: the backend default was the desktop/web landing path.
		const returnSurface = value?.returnSurface ?? "web";
		if (
			typeof value !== "object" ||
			value === null ||
			typeof value.createdAt !== "number" ||
			!Number.isFinite(value.createdAt) ||
			age < 0 ||
			age > DRAFT_LIFETIME_MS ||
			typeof value.idempotencyKey !== "string" ||
			!SAFE_IDEMPOTENCY_KEY.test(value.idempotencyKey) ||
			typeof value.planCode !== "string" ||
			!SAFE_PLAN_CODE.test(value.planCode) ||
			(returnSurface !== "web" && returnSurface !== "pwa") ||
			(value.intentId !== undefined &&
				(typeof value.intentId !== "string" ||
					!SAFE_INTENT_ID.test(value.intentId)))
		) {
			return null;
		}
		return { ...value, returnSurface } as CheckoutDraft;
	} catch {
		return null;
	}
}

function writeDraft(value: CheckoutDraft) {
	try {
		sessionStorage.setItem(DRAFT_KEY, JSON.stringify(value));
	} catch {
		// Checkout remains usable when private browsing blocks session storage.
	}
}

function clearDraft(intentId: string) {
	try {
		const draft = readDraft();
		if (!draft?.intentId || draft.intentId === intentId) {
			sessionStorage.removeItem(DRAFT_KEY);
		}
	} catch {
		// Storage is an optional recovery aid, never a payment authority.
	}
}

function errorMessage(error: unknown) {
	return error instanceof Error
		? error.message
		: "Сервис оплаты временно недоступен.";
}

export function useBillingAccount(options: BillingAccountOptions = {}) {
	const returnSurface = options.returnSurface ?? detectReturnSurface();
	const checkoutInFlight = useRef(false);
	const refreshInFlight = useRef(false);
	const [plans, setPlans] = useState<BillingPlan[]>([]);
	const [payments, setPayments] = useState<BillingPaymentRecord[]>([]);
	const [subscriptions, setSubscriptions] = useState<BillingSubscription[]>([]);
	const [loading, setLoading] = useState(true);
	const [loadError, setLoadError] = useState<string | null>(null);
	const [creatingPlan, setCreatingPlan] = useState<string | null>(null);
	const [payment, setPayment] = useState<BillingPaymentIntent | null>(null);
	const [paymentIntentId, setPaymentIntentId] = useState<string | null>(null);
	const [paymentError, setPaymentError] = useState<string | null>(null);
	const [checkingPayment, setCheckingPayment] = useState(false);
	const [pollGeneration] = useState(0);

	const loadAccount = useCallback(async (signal?: AbortSignal) => {
		setLoading(true);
		setLoadError(null);
		try {
			const [nextPlans, nextSubscriptions, nextPayments] = await Promise.all([
				getBillingPlans(signal),
				getBillingSubscriptions(signal),
				getBillingPayments(signal),
			]);
			setPlans(nextPlans);
			setSubscriptions(nextSubscriptions);
			setPayments(nextPayments);
		} catch (error) {
			if (signal?.aborted) return;
			setLoadError(errorMessage(error));
		} finally {
			if (!signal?.aborted) setLoading(false);
		}
	}, []);

	useEffect(() => {
		const controller = new AbortController();
		void loadAccount(controller.signal);
		return () => controller.abort();
	}, [loadAccount]);

	useEffect(() => {
		const url = new URL(window.location.href);
		const returnedIntent = url.searchParams.get("paymentIntent");
		const recoveredIntent = returnedIntent ?? readDraft()?.intentId ?? null;
		if (recoveredIntent) setPaymentIntentId(recoveredIntent);
		if (returnedIntent) {
			url.searchParams.delete("paymentIntent");
			url.searchParams.delete("account");
			window.history.replaceState(window.history.state, "", url);
		}
	}, []);

	useEffect(() => {
		if (!paymentIntentId) return;
		const controller = new AbortController();
		let timer: ReturnType<typeof setTimeout> | null = null;
		let attempts = 0;
		let stopped = false;

		const inspect = async () => {
			setCheckingPayment(true);
			setPaymentError(null);
			try {
				// Ask the provider directly: this is the fallback that confirms
				// a successful payment even when the bank redirect or webhook
				// never reaches the browser.
				const nextPayment = await refreshBillingPayment(paymentIntentId);
				if (stopped) return;
				setPayment(nextPayment);
				if (TERMINAL_PAYMENT_STATUSES.has(nextPayment.status)) {
					clearDraft(nextPayment.id);
					if (nextPayment.status === "succeeded") {
						await loadAccount(controller.signal);
					}
					return;
				}
				if (nextPayment.status === "unknown") {
					setPaymentError(
						"Банк не подтвердил итоговый статус. Не создавайте повторный платёж — проверка продолжится по этому номеру.",
					);
					return;
				}
				attempts += 1;
				if (attempts >= 30) {
					setPaymentError(
						"Подтверждение занимает больше обычного. Можно проверить статус ещё раз — повторной оплаты не будет.",
					);
					return;
				}
				timer = setTimeout(() => void inspect(), 2_000);
			} catch (error) {
				if (!controller.signal.aborted) setPaymentError(errorMessage(error));
			} finally {
				if (!stopped) setCheckingPayment(false);
			}
		};

		void inspect();
		return () => {
			stopped = true;
			controller.abort();
			if (timer) clearTimeout(timer);
		};
	}, [loadAccount, paymentIntentId, pollGeneration]);

	const beginPayment = useCallback(async (
		planCode: string,
	): Promise<string | null> => {
		if (checkoutInFlight.current) return null;
		checkoutInFlight.current = true;
		setCreatingPlan(planCode);
		setPaymentError(null);
		const previous = readDraft();
		const draft =
			previous?.planCode === planCode &&
			previous.returnSurface === returnSurface
				? previous
				: {
						createdAt: Date.now(),
						idempotencyKey: createBillingIdempotencyKey(),
						planCode,
						returnSurface,
					};
		writeDraft(draft);
		try {
			const nextPayment = await createBillingPayment(
				planCode,
				draft.idempotencyKey,
				returnSurface,
			);
			if (!nextPayment.paymentUrl) {
				throw new BillingApiError(
					502,
					"billing_provider_protocol_error",
					"Банк не вернул ссылку на оплату.",
				);
			}
			writeDraft({ ...draft, intentId: nextPayment.id });
			setPayment(nextPayment);
			setPaymentIntentId(nextPayment.id);
			return nextPayment.paymentUrl;
		} catch (error) {
			setPaymentError(errorMessage(error));
			return null;
		} finally {
			checkoutInFlight.current = false;
			setCreatingPlan(null);
		}
	}, []);

	const updateAutoRenew = useCallback(async (
		subscriptionId: string,
		enabled: boolean,
	) => {
		const next = await setBillingAutoRenew(subscriptionId, enabled);
		setSubscriptions((current) =>
			current.map((entry) =>
				entry.id === next.id ? next : entry,
			),
		);
	}, []);

	const refreshPayment = useCallback(async () => {
		if (!paymentIntentId || refreshInFlight.current) return;
		refreshInFlight.current = true;
		setCheckingPayment(true);
		setPaymentError(null);
		try {
			const nextPayment = await refreshBillingPayment(paymentIntentId);
			setPayment(nextPayment);
			if (TERMINAL_PAYMENT_STATUSES.has(nextPayment.status)) {
				clearDraft(nextPayment.id);
				if (nextPayment.status === "succeeded") {
					await loadAccount();
				}
			}
		} catch (error) {
			setPaymentError(errorMessage(error));
		} finally {
			refreshInFlight.current = false;
			setCheckingPayment(false);
		}
	}, [loadAccount, paymentIntentId]);

	return {
		beginPayment,
		checkingPayment,
		continuePayment: () => payment?.paymentUrl ?? null,
		creatingPlan,
		loadError,
		loading,
		payments,
		payment,
		paymentError,
		plans,
		refreshAccount: () => void loadAccount(),
		refreshPayment,
		subscriptions,
		updateAutoRenew,
	};
}

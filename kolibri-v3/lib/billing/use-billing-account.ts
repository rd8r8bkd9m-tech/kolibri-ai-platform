"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
	type BillingPaymentIntent,
	type BillingPlan,
	type BillingSubscription,
	createBillingIdempotencyKey,
	createBillingPayment,
	getBillingPayment,
	getBillingPlans,
	getBillingSubscriptions,
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
};

function readDraft(): CheckoutDraft | null {
	try {
		const value = JSON.parse(sessionStorage.getItem(DRAFT_KEY) ?? "null");
		const age = Date.now() - Number(value?.createdAt);
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
			(value.intentId !== undefined &&
				(typeof value.intentId !== "string" ||
					!SAFE_INTENT_ID.test(value.intentId)))
		) {
			return null;
		}
		return value as CheckoutDraft;
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

export function useBillingAccount() {
	const checkoutInFlight = useRef(false);
	const [plans, setPlans] = useState<BillingPlan[]>([]);
	const [subscriptions, setSubscriptions] = useState<BillingSubscription[]>([]);
	const [loading, setLoading] = useState(true);
	const [loadError, setLoadError] = useState<string | null>(null);
	const [creatingPlan, setCreatingPlan] = useState<string | null>(null);
	const [payment, setPayment] = useState<BillingPaymentIntent | null>(null);
	const [paymentIntentId, setPaymentIntentId] = useState<string | null>(null);
	const [paymentError, setPaymentError] = useState<string | null>(null);
	const [checkingPayment, setCheckingPayment] = useState(false);
	const [pollGeneration, setPollGeneration] = useState(0);

	const loadAccount = useCallback(async (signal?: AbortSignal) => {
		setLoading(true);
		setLoadError(null);
		try {
			const [nextPlans, nextSubscriptions] = await Promise.all([
				getBillingPlans(signal),
				getBillingSubscriptions(signal),
			]);
			setPlans(nextPlans);
			setSubscriptions(nextSubscriptions);
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
				const nextPayment = await getBillingPayment(
					paymentIntentId,
					controller.signal,
				);
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

	const beginPayment = useCallback(async (planCode: string) => {
		if (checkoutInFlight.current) return;
		checkoutInFlight.current = true;
		setCreatingPlan(planCode);
		setPaymentError(null);
		const previous = readDraft();
		const draft =
			previous?.planCode === planCode
				? previous
				: {
						createdAt: Date.now(),
						idempotencyKey: createBillingIdempotencyKey(),
						planCode,
					};
		writeDraft(draft);
		try {
			const nextPayment = await createBillingPayment(
				planCode,
				draft.idempotencyKey,
			);
			writeDraft({ ...draft, intentId: nextPayment.id });
			setPayment(nextPayment);
			setPaymentIntentId(nextPayment.id);
			if (nextPayment.paymentUrl) window.location.assign(nextPayment.paymentUrl);
		} catch (error) {
			setPaymentError(errorMessage(error));
		} finally {
			checkoutInFlight.current = false;
			setCreatingPlan(null);
		}
	}, []);

	return {
		beginPayment,
		checkingPayment,
		continuePayment: () => {
			if (payment?.paymentUrl) window.location.assign(payment.paymentUrl);
		},
		creatingPlan,
		loadError,
		loading,
		payment,
		paymentError,
		plans,
		refreshAccount: () => void loadAccount(),
		refreshPayment: () => setPollGeneration((value) => value + 1),
		subscriptions,
	};
}

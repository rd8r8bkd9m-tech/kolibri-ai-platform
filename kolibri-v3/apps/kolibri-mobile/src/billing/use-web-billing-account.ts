import { useCallback, useEffect, useRef, useState } from "react";

import {
	type AuthorizedFetch,
	type BillingPaymentIntent,
	type BillingPlan,
	type BillingSubscription,
	createWebBillingIdempotencyKey,
	createWebBillingPayment,
	getWebBillingPayment,
	getWebBillingPayments,
	getWebBillingPlans,
	getWebBillingSubscriptions,
} from "@/src/billing/client";

const DRAFT_KEY = "kolibri.billing.pwa-checkout.v1";
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

type UseWebBillingAccountInput = {
	authorizedFetch: AuthorizedFetch;
	onEntitlementChanged: () => Promise<unknown>;
	returnedIntent?: string;
};

const readDraft = (): CheckoutDraft | null => {
	try {
		const value = JSON.parse(
			globalThis.sessionStorage.getItem(DRAFT_KEY) ?? "null",
		) as unknown;
		if (typeof value !== "object" || value === null) return null;
		const draft = value as Partial<CheckoutDraft>;
		const age = Date.now() - Number(draft.createdAt);
		if (
			typeof draft.createdAt !== "number" ||
			!Number.isFinite(draft.createdAt) ||
			age < 0 ||
			age > DRAFT_LIFETIME_MS ||
			typeof draft.idempotencyKey !== "string" ||
			!SAFE_IDEMPOTENCY_KEY.test(draft.idempotencyKey) ||
			typeof draft.planCode !== "string" ||
			!SAFE_PLAN_CODE.test(draft.planCode) ||
			(draft.intentId !== undefined &&
				(typeof draft.intentId !== "string" ||
					!SAFE_INTENT_ID.test(draft.intentId)))
		) {
			return null;
		}
		return draft as CheckoutDraft;
	} catch {
		return null;
	}
};

const writeDraft = (value: CheckoutDraft) => {
	try {
		globalThis.sessionStorage.setItem(DRAFT_KEY, JSON.stringify(value));
	} catch {
		// Session storage is only a checkout recovery aid.
	}
};

const clearDraft = (intentId: string) => {
	try {
		const draft = readDraft();
		if (!draft?.intentId || draft.intentId === intentId) {
			globalThis.sessionStorage.removeItem(DRAFT_KEY);
		}
	} catch {
		// Payment state remains server-authoritative when storage is unavailable.
	}
};

const consumeReturnParameter = () => {
	try {
		const url = new URL(globalThis.location.href);
		url.searchParams.delete("paymentIntent");
		globalThis.history.replaceState(globalThis.history.state, "", url);
	} catch {
		// A cosmetic URL cleanup must never interrupt payment reconciliation.
	}
};

const errorMessage = (error: unknown) =>
	error instanceof Error
		? error.message
		: "Сервис оплаты временно недоступен.";

export function useWebBillingAccount({
	authorizedFetch,
	onEntitlementChanged,
	returnedIntent,
}: UseWebBillingAccountInput) {
	const checkoutInFlight = useRef(false);
	const [plans, setPlans] = useState<BillingPlan[]>([]);
	const [subscriptions, setSubscriptions] = useState<BillingSubscription[]>([]);
	const [payments, setPayments] = useState<BillingPaymentIntent[]>([]);
	const [loading, setLoading] = useState(true);
	const [loadError, setLoadError] = useState<string | null>(null);
	const [creatingPlan, setCreatingPlan] = useState<string | null>(null);
	const [payment, setPayment] = useState<BillingPaymentIntent | null>(null);
	const [paymentIntentId, setPaymentIntentId] = useState<string | null>(() => {
		const safeReturnedIntent =
			returnedIntent && SAFE_INTENT_ID.test(returnedIntent)
				? returnedIntent
				: null;
		return safeReturnedIntent ?? readDraft()?.intentId ?? null;
	});
	const [paymentError, setPaymentError] = useState<string | null>(null);
	const [checkingPayment, setCheckingPayment] = useState(false);
	const [pollGeneration, setPollGeneration] = useState(0);

	const loadAccount = useCallback(
		async (signal?: AbortSignal) => {
			try {
				const [nextPlans, nextSubscriptions, nextPayments] = await Promise.all([
					getWebBillingPlans(authorizedFetch, signal),
					getWebBillingSubscriptions(authorizedFetch, signal),
					getWebBillingPayments(authorizedFetch, signal),
				]);
				if (signal?.aborted) return;
				setPlans(nextPlans);
				setSubscriptions(nextSubscriptions);
				setPayments(nextPayments);
				setLoadError(null);
			} catch (error) {
				if (!signal?.aborted) setLoadError(errorMessage(error));
			} finally {
				if (!signal?.aborted) setLoading(false);
			}
		},
		[authorizedFetch],
	);

	useEffect(() => {
		const controller = new AbortController();
		const timer = setTimeout(() => void loadAccount(controller.signal), 0);
		return () => {
			clearTimeout(timer);
			controller.abort();
		};
	}, [loadAccount]);

	useEffect(() => {
		if (returnedIntent) consumeReturnParameter();
	}, [returnedIntent]);

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
				const nextPayment = await getWebBillingPayment(
					authorizedFetch,
					paymentIntentId,
					controller.signal,
				);
				if (stopped) return;
				setPayment(nextPayment);
				if (TERMINAL_PAYMENT_STATUSES.has(nextPayment.status)) {
					clearDraft(nextPayment.id);
					if (nextPayment.status === "succeeded") {
						await Promise.all([
							loadAccount(controller.signal),
							onEntitlementChanged(),
						]);
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
						"Подтверждение занимает больше обычного. Проверьте статус ещё раз — повторной оплаты не будет.",
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
	}, [
		authorizedFetch,
		loadAccount,
		onEntitlementChanged,
		paymentIntentId,
		pollGeneration,
	]);

	const beginPayment = useCallback(
		async (planCode: string) => {
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
							idempotencyKey: createWebBillingIdempotencyKey(),
							planCode,
						};
			writeDraft(draft);
			try {
				const nextPayment = await createWebBillingPayment(
					authorizedFetch,
					planCode,
					draft.idempotencyKey,
				);
				writeDraft({ ...draft, intentId: nextPayment.id });
				setPayment(nextPayment);
				setPaymentIntentId(nextPayment.id);
				if (nextPayment.paymentUrl) {
					globalThis.location.assign(nextPayment.paymentUrl);
				}
			} catch (error) {
				setPaymentError(errorMessage(error));
			} finally {
				checkoutInFlight.current = false;
				setCreatingPlan(null);
			}
		},
		[authorizedFetch],
	);

	return {
		beginPayment,
		checkingPayment,
		continuePayment: () => {
			if (payment?.paymentUrl) globalThis.location.assign(payment.paymentUrl);
		},
		creatingPlan,
		loadError,
		loading,
		payment,
		paymentError,
		payments,
		plans,
		refreshAccount: () => {
			setLoading(true);
			setLoadError(null);
			void loadAccount();
		},
		refreshPayment: () => setPollGeneration((value) => value + 1),
		subscriptions,
	};
}

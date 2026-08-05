"use client";

import Link from "next/link";
import { ArrowRight, CircleAlert, LoaderCircle } from "lucide-react";
import { useState } from "react";
import { BillingCheckoutOverlay } from "@/components/billing/billing-checkout-overlay";
import {
	createBillingIdempotencyKey,
	BillingApiError,
	createBillingPayment,
} from "@/lib/billing/client";

type BillingCheckoutError = {
	title: string;
	details: string;
	auth?: boolean;
};

function mapPaymentError(error: unknown): BillingCheckoutError {
	if (error instanceof BillingApiError) {
		if (error.status === 401) {
			return {
				title: "Нужна авторизация",
				details: "Войдите в аккаунт, чтобы создать платёж.",
				auth: true,
			};
		}
		return {
			title: "Не удалось создать оплату",
			details: error.message || "Сервис оплаты временно недоступен.",
		};
	}
	if (error instanceof Error) {
		return { title: "Не удалось создать оплату", details: error.message };
	}
	return {
		title: "Не удалось создать оплату",
		details: "Сервис оплаты временно недоступен.",
	};
}

export function PublicPlanCheckoutButton({ planCode }: { planCode: string }) {
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState<BillingCheckoutError | null>(null);
	const [paymentUrl, setPaymentUrl] = useState<string | null>(null);

	const startCheckout = async () => {
		if (busy) return;
		setBusy(true);
		setError(null);

		try {
			const paymentIntent = await createBillingPayment(
				planCode,
				createBillingIdempotencyKey(),
				"web",
			);
			if (paymentIntent.paymentUrl) {
				setPaymentUrl(paymentIntent.paymentUrl);
				return;
			}
			throw new Error("Банк не вернул ссылку на оплату.");
		} catch (nextError) {
			setError(mapPaymentError(nextError));
		} finally {
			setBusy(false);
		}
	};

	return (
		<div>
			{paymentUrl ? (
				<BillingCheckoutOverlay
					open
					paymentUrl={paymentUrl}
					onClose={() => setPaymentUrl(null)}
				/>
			) : null}
			{error?.auth ? (
				<Link className="kp-button kp-button-primary" href="/app?account=billing">
					Войти и оплатить <ArrowRight aria-hidden="true" />
				</Link>
			) : (
				<button
					type="button"
					onClick={startCheckout}
					disabled={busy}
					className="kp-button kp-button-primary"
				>
					{busy ? (
						<LoaderCircle className="kp-spin size-4" aria-hidden="true" />
					) : null}
					<span>{busy ? "Подготавливаем..." : "Оплатить"}</span>
				</button>
			)}
			{error ? (
				<small>
					<CircleAlert
						className="mr-1 inline-block size-3.5"
						aria-hidden="true"
					/>
					{" "}
					<strong>{error.title}:</strong> {error.details}
				</small>
			) : null}
		</div>
	);
}

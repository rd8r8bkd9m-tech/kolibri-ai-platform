import type { Metadata } from "next";
import Link from "next/link";
import { PublicShell } from "@/components/public-site/public-shell";
import { getPublicCommerceConfig } from "@/lib/server/public-commerce";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
	title: "Оплата прошла успешно",
	description: "Платёж подтверждён. Доступ активируется автоматически.",
};

export default function PaymentSuccessPage() {
	const commerce = getPublicCommerceConfig();
	return (
		<PublicShell commerce={commerce}>
			<main className="kp-payment-result is-success">
				<div className="kp-container">
					<h1>Оплата прошла успешно</h1>
					<p>
						Платёж подтверждён банком. Доступ к сервису активируется автоматически
						и появится в личном кабинете.
					</p>
					<Link className="kp-button kp-button-primary" href="/app?account=billing">
						Перейти в личный кабинет
					</Link>
				</div>
			</main>
		</PublicShell>
	);
}

import type { Metadata } from "next";
import Link from "next/link";
import { PublicShell } from "@/components/public-site/public-shell";
import { getPublicCommerceConfig } from "@/lib/server/public-commerce";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
	title: "Оплата не завершена",
	description: "Платёж не был подтверждён. Попробуйте ещё раз.",
};

export default function PaymentFailPage() {
	const commerce = getPublicCommerceConfig();
	return (
		<PublicShell commerce={commerce}>
			<main className="kp-payment-result is-fail">
				<div className="kp-container">
					<h1>Оплата не завершена</h1>
					<p>
						Банк не подтвердил платёж. Деньги не списаны; при необходимости повторите
						оплату или обратитесь в поддержку.
					</p>
					<Link className="kp-button kp-button-primary" href="/app?account=billing">
						Вернуться в личный кабинет
					</Link>
				</div>
			</main>
		</PublicShell>
	);
}

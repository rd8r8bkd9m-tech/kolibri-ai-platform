import Link from "next/link";
import { Suspense } from "react";
import { CreditCard, KeyRound, RefreshCcw, ShieldCheck } from "lucide-react";
import {
	PublicPlanCatalog,
	PublicPlanCatalogFallback,
} from "../public-plan-catalog";

export function CommerceSection() {
	return (
		<section className="kp-commerce kp-section" id="pricing" aria-labelledby="commerce-title">
			<div className="kp-container kp-commerce-grid">
				<div>
					<div className="kp-section-heading">
						<p className="kp-eyebrow kp-eyebrow-dark"><span /> Доступ и оплата</p>
						<h2 id="commerce-title">Понятный путь от выбора тарифа до доступа.</h2>
						<p>Условия оплаты и цифровой поставки опубликованы до перехода в банк.</p>
					</div>
					<div className="kp-commerce-points">
						<div><CreditCard /><p><strong>Оплата в Т‑Банке</strong><span>Kolibri не получает данные банковской карты.</span></p></div>
						<div><KeyRound /><p><strong>Цифровой доступ</strong><span>Активируется только после статуса CONFIRMED.</span></p></div>
						<div><RefreshCcw /><p><strong>Отмена и возврат</strong><span>Порядок обращения опубликован отдельной страницей.</span></p></div>
						<div><ShieldCheck /><p><strong>Серверный каталог</strong><span>Название, срок и цена тарифа приходят из биллинга.</span></p></div>
					</div>
					<Link className="kp-text-link" href="/legal/payment-and-refund">
						Условия оплаты, отмены и возврата →
					</Link>
				</div>
				<Suspense fallback={<PublicPlanCatalogFallback compact />}>
					<PublicPlanCatalog compact />
				</Suspense>
			</div>
		</section>
	);
}

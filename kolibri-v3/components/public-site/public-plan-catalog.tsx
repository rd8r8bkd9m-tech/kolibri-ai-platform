import { Check, CircleAlert } from "lucide-react";
import Link from "next/link";
import { getPublicLaunchPlan } from "@/lib/server/public-billing";
import { PublicPlanCheckoutButton } from "./landing/public-plan-checkout-button";

const rubles = new Intl.NumberFormat("ru-RU", {
	style: "currency",
	currency: "RUB",
	maximumFractionDigits: 2,
});

function durationLabel(seconds: number) {
	const days = Math.round(seconds / 86_400);
	return days % 10 === 1 && days % 100 !== 11
		? `${days} день`
		: days % 10 >= 2 && days % 10 <= 4 && (days % 100 < 10 || days % 100 >= 20)
			? `${days} дня`
			: `${days} дней`;
}

export function PublicPlanCatalogFallback({ compact = false }: { compact?: boolean }) {
	const fallbackNote = "Цена не подставляется вручную и появится только из каталога биллинга.";

	return (
		<div
			className={`kp-plan-state is-loading${compact ? " is-compact" : ""}`}
			role="status"
			aria-live="polite"
		>
			<div className="kp-plan-loading-line" aria-hidden="true" />
			<div>
				<strong>Тариф готовится к публикации</strong>
				<p>Серверный каталог тарифов временно недоступен.</p>
				<p>{fallbackNote}</p>
			</div>
		</div>
	);
}

export async function PublicPlanCatalog({ compact = false }: { compact?: boolean }) {
	const { plan } = await getPublicLaunchPlan();
	const fallbackNote = "Цена не подставляется вручную и появится только из каталога биллинга.";

	if (!plan) {
		return (
			<div className="kp-plan-state is-warning" role="status">
				<CircleAlert aria-hidden="true" />
				<div>
					<strong>Тариф готовится к публикации</strong>
					<p>Серверный каталог тарифов временно недоступен.</p>
					<p>{fallbackNote}</p>
				</div>
			</div>
		);
	}

	return (
		<article className={`kp-public-plan${compact ? " is-compact" : ""}`}>
			<div className="kp-plan-copy">
				<p className="kp-plan-label">Единый тариф запуска</p>
				<h3>{plan.name}</h3>
				<p className="kp-plan-price">{rubles.format(plan.amountMinor / 100)}</p>
				<p className="kp-plan-duration">Разовая оплата · доступ на {durationLabel(plan.durationSeconds)}</p>
			</div>
			<ul>
				<li><Check /> Проекты и версионные сметы</li>
				<li><Check /> Связанные документы</li>
				<li><Check /> Доступ после подтверждения банка</li>
			</ul>
			<div className="kp-plan-action">
				<PublicPlanCheckoutButton planCode={plan.code} />
				<small>Оплата выполняется в личном кабинете на защищённой странице Т‑Банка.</small>
			</div>
			<div className="klp-payment-methods" role="group" aria-label="Способы оплаты">
				<span>Оплата принимается:</span>
				<span className="klp-payment-badge">МИР</span>
				<span className="klp-payment-badge">Visa</span>
				<span className="klp-payment-badge">Mastercard</span>
				<span className="klp-payment-badge">СБП</span>
				<span className="klp-payment-badge">T‑Pay</span>
				<Link
					href="https://tbank.ru"
					target="_blank"
					rel="noopener noreferrer"
					style={{ color: "var(--klp-mint)", textDecoration: "underline" }}
				>
					Банк — tbank.ru
				</Link>
			</div>
		</article>
	);
}

import Link from "next/link";
import { ArrowRight, Check, CircleAlert } from "lucide-react";
import { getPublicLaunchPlan } from "@/lib/server/public-billing";

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

export async function PublicPlanCatalog({ compact = false }: { compact?: boolean }) {
	const { error, plan } = await getPublicLaunchPlan();
	if (!plan) {
		return (
			<div className="kp-plan-state is-warning" role="status">
				<CircleAlert aria-hidden="true" />
				<div>
					<strong>Тариф готовится к публикации</strong>
					<p>
						{error}
					</p>
					<p>Цена не подставляется вручную и появится только из каталога биллинга.</p>
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
				<Link className="kp-button kp-button-primary" href="/app">
					Войти и оплатить <ArrowRight aria-hidden="true" />
				</Link>
				<small>Оплата выполняется в личном кабинете на защищённой странице Т‑Банка.</small>
			</div>
		</article>
	);
}

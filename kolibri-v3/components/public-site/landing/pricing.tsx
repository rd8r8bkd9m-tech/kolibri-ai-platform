import Link from "next/link";
import { Check } from "lucide-react";
import type { ReactNode } from "react";
import type { BillingPlan } from "@/lib/billing/client";
import { getPublicLaunchPlan } from "@/lib/server/public-billing";
import { PublicPlanCheckoutButton } from "./public-plan-checkout-button";

function durationLabel(seconds: number) {
	const days = Math.round(seconds / 86_400);
	return days % 10 === 1 && days % 100 !== 11
		? `${days} день`
		: days % 10 >= 2 && days % 10 <= 4 && (days % 100 < 10 || days % 100 >= 20)
			? `${days} дня`
			: `${days} дней`;
}

const rubles = new Intl.NumberFormat("ru-RU", {
	style: "currency",
	currency: "RUB",
	maximumFractionDigits: 0,
});

function PriceCard({
	name,
	badge,
	subtitle,
	price,
	period,
	features,
	cta,
	featured = false,
}: {
	name: string;
	badge?: string;
	subtitle: string;
	price: string;
	period: string;
	features: string[];
	cta: ReactNode;
	featured?: boolean;
}) {
	return (
		<article className={`klp-price-card${featured ? " is-featured" : ""}`}>
			<div className="klp-price-name">
				{name}
				{badge ? <span className="klp-price-badge">{badge}</span> : null}
			</div>
			<p className="klp-price-sub">{subtitle}</p>
			<div className="klp-price-value">{price}</div>
			<div className="klp-price-period">{period}</div>
			<div style={{ marginTop: "auto" }}>{cta}</div>
			<ul className="klp-price-features">
				{features.map((feature) => (
					<li key={feature}><Check aria-hidden="true" /> {feature}</li>
				))}
			</ul>
		</article>
	);
}

function PricingGrid({ plan }: { plan: BillingPlan | null }) {
	const serverPrice = plan ? rubles.format(plan.amountMinor / 100) : "—";
	const serverPeriod = plan ? `Разовая оплата · ${durationLabel(plan.durationSeconds)}` : "из каталога биллинга";

	return (
		<>
			<div className="klp-pricing-toggle" role="group" aria-label="Период оплаты">
				<button className="is-active" type="button">Ежемесячно</button>
				<button type="button" disabled aria-label="Ежегодная оплата скоро">
					Ежегодно <small>скоро</small>
				</button>
			</div>
			<div className="klp-pricing-grid">
				<PriceCard
					name="Бесплатный"
					subtitle="Познакомиться в чате — без карты"
					price="0 ₽"
					period="/ месяц"
					features={[
						"Регистрация без карты",
						"Чат с агентом",
						"Проекты и версии смет",
						"Демо-экспорт документов",
					]}
					cta={<Link className="klp-price-cta" href="/app">Попробовать бесплатно</Link>}
				/>
				<PriceCard
					name="Pro"
					badge="Популярный"
					subtitle="Регулярная работа со сметами, документами и нормативами"
					price={serverPrice}
					period={serverPeriod}
					features={[
						"Полный контур: смета, КП, договор, акт",
						"ФСНБ-2022, ГЭСН и цены ФГИС ЦС",
						"Экспорт XLSX, PDF, DOCX",
						"Версии и основания расчёта",
						"Оплата через защищённую страницу Т‑Банка",
					]}
					cta={
						plan ? (
							<PublicPlanCheckoutButton planCode={plan.code} />
						) : (
							<Link className="klp-price-cta" href="/pricing">Посмотреть тариф</Link>
						)
					}
					featured
				/>
				<PriceCard
					name="Max"
					subtitle="Для команд и потоков проектов"
					price="по запросу"
					period="/ месяц"
					features={[
						"Общий каталог проектов",
						"Роли и доступы команды",
						"Единый биллинг",
						"Приоритетная поддержка",
					]}
					cta={<Link className="klp-price-cta" href="/contacts">Обсудить</Link>}
				/>
				<PriceCard
					name="Командный"
					subtitle="Корпоративный доступ и договор"
					price="по запросу"
					period="/ чел. / месяц"
					features={[
						"Выделенные контуры и справочники",
						"Интеграции с 1С и CRM",
						"Аудит и журналы операций",
						"Договор и счёт для юрлиц",
					]}
					cta={<Link className="klp-price-cta" href="/contacts">Обсудить</Link>}
				/>
			</div>
			<p style={{ marginTop: "2rem", color: "var(--klp-faint)", fontSize: "0.78rem", textAlign: "center" }}>
				Цена тарифа загружается из серверного каталога биллинга и не подставляется вручную.{" "}
				<Link href="/legal/payment-and-refund" style={{ color: "var(--klp-mint)", textDecoration: "underline" }}>
					Условия оплаты и возврата
				</Link>
			</p>
		</>
	);
}

export async function PricingSection() {
	const { plan } = await getPublicLaunchPlan();
	return (
		<section className="klp-pricing" id="pricing" aria-labelledby="pricing-title">
			<div className="klp-pricing-inner">
				<header className="klp-pricing-head">
					<h2 id="pricing-title">Тарифы</h2>
					<p>
						Начните бесплатно, а для регулярной работы выберите единый тариф запуска:
						название, срок и цена приходят из серверного каталога.
					</p>
				</header>
				<PricingGrid plan={plan} />
			</div>
		</section>
	);
}

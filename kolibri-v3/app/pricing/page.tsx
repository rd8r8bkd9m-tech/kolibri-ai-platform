import type { Metadata } from "next";
import Link from "next/link";
import { PublicPlanCatalog } from "@/components/public-site/public-plan-catalog";
import { PublicShell } from "@/components/public-site/public-shell";
import { getPublicCommerceConfig } from "@/lib/server/public-commerce";

export const metadata: Metadata = {
	title: "Тарифы",
	description: "Тариф Kolibri AI из официального серверного каталога биллинга.",
};

export default function PricingPage() {
	const commerce = getPublicCommerceConfig();
	return (
		<PublicShell commerce={commerce}>
			<section className="kp-public-page kp-section" id="plans">
				<div className="kp-container kp-pricing-layout">
					<header className="kp-page-heading">
						<p className="kp-eyebrow kp-eyebrow-dark"><span /> Тарифы</p>
						<h1>Один понятный тариф на старте.</h1>
						<p>
							Название, стоимость и срок доступа загружаются из серверного каталога.
							Публичная страница не хранит и не подменяет цену.
						</p>
					</header>
					<PublicPlanCatalog />
					<div className="kp-pricing-notes">
						<h2>Как получить доступ</h2>
						<ol>
							<li><span>1</span><p><strong>Войдите в Kolibri</strong>Платёж привязывается к вашей учётной записи.</p></li>
							<li><span>2</span><p><strong>Перейдите в Т‑Банк</strong>Оплата проходит на защищённой странице банка.</p></li>
							<li><span>3</span><p><strong>Дождитесь CONFIRMED</strong>Доступ включается после серверного подтверждения оплаты.</p></li>
						</ol>
						<p>
							Подробнее: <Link href="/legal/payment-and-refund">оплата, отмена и возврат</Link>.
						</p>
					</div>
				</div>
			</section>
		</PublicShell>
	);
}

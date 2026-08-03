import type { Metadata } from "next";
import { Mail, MapPin, Phone } from "lucide-react";
import { LegalFacts } from "@/components/public-site/legal/legal-page";
import { PublicShell } from "@/components/public-site/public-shell";
import { getPublicCommerceConfig } from "@/lib/server/public-commerce";

export const metadata: Metadata = { title: "Контакты" };
export const dynamic = "force-dynamic";

export default function ContactsPage() {
	const commerce = getPublicCommerceConfig();
	return (
		<PublicShell commerce={commerce}>
			<section className="kp-public-page kp-section">
				<div className="kp-container kp-contact-layout">
					<header className="kp-page-heading">
						<p className="kp-eyebrow kp-eyebrow-dark"><span /> Связаться с нами</p>
						<h1>Контакты и реквизиты</h1>
						<p>Поддержка по работе сервиса, заказам, оплате и возвратам.</p>
					</header>
					<div className="kp-contact-grid">
						<article><Mail /><span>Электронная почта</span><strong>{commerce.email ?? "Не настроено"}</strong></article>
						<article><Phone /><span>Телефон</span><strong>{commerce.phone ?? "Не настроено"}</strong></article>
						<article><MapPin /><span>Адрес</span><strong>{commerce.address ?? "Не настроено"}</strong></article>
					</div>
					<LegalFacts items={[
						{ label: "Продавец", value: commerce.legalName },
						{ label: "ИНН", value: commerce.inn },
						{ label: "Налоговый статус", value: commerce.taxStatus },
					]} />
					{!commerce.ready ? (
						<div className="kp-legal-status is-warning" role="status">
							<strong>Контактный блок не готов к публикации</strong>
							<span>Заполните серверную legal-конфигурацию. Значения не подставляются фиктивно.</span>
						</div>
					) : null}
				</div>
			</section>
		</PublicShell>
	);
}

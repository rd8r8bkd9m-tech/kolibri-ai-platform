import type { Metadata } from "next";
import Link from "next/link";
import {
	LegalFacts,
	LegalPage,
	LegalSection,
} from "@/components/public-site/legal/legal-page";
import { PublicShell } from "@/components/public-site/public-shell";
import { getPublicCommerceConfig } from "@/lib/server/public-commerce";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
	title: "Информация для покупателей",
	description:
		"Требования интернет-магазина: описание услуги, оплата, доставка, возврат, безопасность и реквизиты продавца.",
};

export default function StoreInfoPage() {
	const commerce = getPublicCommerceConfig();
	return (
		<PublicShell commerce={commerce}>
			<LegalPage
				commerce={commerce}
				eyebrow="Магазин"
				title="Информация для покупателей"
				lead="Раздел подготовлен в соответствии с требованиями к интернет-магазину платёжных систем."
			>
				{!commerce.ready ? (
					<p className="kp-legal-important">
						До публикации всех реквизитов раздел содержит общие условия; реквизиты продавца
						публикуются после подтверждения учётных данных.
					</p>
				) : null}
				<LegalSection title="1. Описание услуги">
					<p>
						КолИ (Kolibri) — программный сервис для подготовки строительных смет и связанных
						документов. Услуга предоставляется в электронном виде через личный кабинет.
						Страна производителя услуги — Российская Федерация.
					</p>
				</LegalSection>
				<LegalSection title="2. Способы оплаты">
					<p>
						Оплата принимается на защищённой странице Т‑Банка: банковские карты (МИР, Visa,
						Mastercard), СБП, T‑Pay и другие способы, доступные терминалу. Kolibri не принимает
						и не хранит реквизиты карт.
					</p>
					<p>
						Банк:{" "}
						<Link href="https://tbank.ru" target="_blank" rel="noopener noreferrer">
							tbank.ru
						</Link>
						.
					</p>
				</LegalSection>
				<LegalSection title="3. Порядок и сроки предоставления доступа">
					<p>
						Доступ к оплаченной услуге активируется автоматически после подтверждения платежа
						банком (CONFIRMED) и предоставляется в электронном виде без физической доставки.
						Регион предоставления — без ограничений, при технической доступности сервиса.
					</p>
				</LegalSection>
				<LegalSection title="4. Отмена и возврат">
					<p>
						Условия и порядок отмены и возврата приведены на странице{" "}
						<Link href="/legal/payment-and-refund">«Оплата и возврат»</Link>.
					</p>
				</LegalSection>
				<LegalSection title="5. Экспортные ограничения">
					<p>Экспортные ограничения на предоставление услуги отсутствуют.</p>
				</LegalSection>
				<LegalSection title="6. Информационная безопасность">
					<p>
						Соединение с сервисом защищено протоколом TLS. Платёжные данные вводятся
						непосредственно на стороне Т‑Банка и передаются банку по защищённым каналам;
						Kolibri не обрабатывает и не хранит PAN, срок действия, CVV и иные конфиденциальные
						платёжные данные. Подробнее —{" "}
						<Link href="/legal/privacy">политика конфиденциальности</Link>.
					</p>
				</LegalSection>
				<LegalSection title="7. Контакты и реквизиты продавца">
					{commerce.ready ? (
						<LegalFacts
							items={[
								{ label: "Наименование", value: commerce.legalName },
								{ label: "ИНН", value: commerce.inn },
								{ label: "Налоговый статус", value: commerce.taxStatus },
								{ label: "Адрес", value: commerce.address },
								{ label: "Поддержка", value: commerce.email },
								{ label: "Телефон", value: commerce.phone },
							]}
						/>
					) : (
						<p>
							Реквизиты продавца и контакты службы поддержки публикуются после подтверждения
							учётных данных продавца. Контакты сервиса — на странице{" "}
							<Link href="/contacts">«Контакты»</Link>.
						</p>
					)}
				</LegalSection>
			</LegalPage>
		</PublicShell>
	);
}

import type { Metadata } from "next";
import { LegalFacts, LegalPage, LegalSection } from "@/components/public-site/legal/legal-page";
import { PublicShell } from "@/components/public-site/public-shell";
import { getPublicCommerceConfig } from "@/lib/server/public-commerce";

export const metadata: Metadata = { title: "Политика конфиденциальности" };
export const dynamic = "force-dynamic";

export default function PrivacyPage() {
	const commerce = getPublicCommerceConfig();
	return (
		<PublicShell commerce={commerce}>
			<LegalPage
				commerce={commerce}
				eyebrow="Юридические документы"
				title="Политика конфиденциальности"
				lead="Какие данные нужны Kolibri AI для работы сервиса и обработки обращений."
			>
				<LegalSection title="1. Оператор данных">
					<LegalFacts items={[
						{ label: "Оператор", value: commerce.legalName },
						{ label: "ИНН", value: commerce.inn },
						{ label: "Контакт", value: commerce.email },
					]} />
				</LegalSection>
				<LegalSection title="2. Какие данные обрабатываются">
					<p>
						Данные учётной записи и сессии, контактные сведения, содержимое проектов и файлов,
						команды в чате, технические журналы, сведения о выбранном тарифе и статусе платежа.
						Kolibri не получает полный номер и защитный код банковской карты.
					</p>
				</LegalSection>
				<LegalSection title="3. Для чего нужны данные">
					<p>
						Для предоставления доступа, сохранения проектов, выполнения пользовательских команд,
						поддержки, защиты сервиса, выполнения обязательств по оплате и обработки законных обращений.
					</p>
				</LegalSection>
				<LegalSection title="4. Передача и хранение">
					<p>
						Данные передаются только поставщикам инфраструктуры и платёжному провайдеру в объёме,
						необходимом для соответствующей операции, либо по требованию закона. Срок хранения
						определяется целью обработки, договорными и обязательными требованиями.
					</p>
				</LegalSection>
				<LegalSection title="5. Права пользователя">
					<p>
						Пользователь может запросить сведения об обработке, уточнение или удаление данных,
						если их сохранение больше не требуется по договору или закону. Запрос направляется
						по опубликованному адресу электронной почты.
					</p>
				</LegalSection>
			</LegalPage>
		</PublicShell>
	);
}

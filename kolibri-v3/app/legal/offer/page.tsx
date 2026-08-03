import type { Metadata } from "next";
import { LegalFacts, LegalPage, LegalSection } from "@/components/public-site/legal/legal-page";
import { PublicShell } from "@/components/public-site/public-shell";
import { getPublicCommerceConfig } from "@/lib/server/public-commerce";

export const metadata: Metadata = { title: "Публичная оферта" };
export const dynamic = "force-dynamic";

export default function OfferPage() {
	const commerce = getPublicCommerceConfig();
	return (
		<PublicShell commerce={commerce}>
			<LegalPage
				commerce={commerce}
				eyebrow="Юридические документы"
				title="Публичная оферта"
				lead="Условия предоставления цифрового доступа к сервису Kolibri AI."
			>
				{!commerce.ready ? (
					<p className="kp-legal-important">
						До публикации всех реквизитов эта страница является проектом условий и не считается предложением заключить договор.
					</p>
				) : null}
				<LegalSection title="1. Продавец и сервис">
					<LegalFacts items={[
						{ label: "Продавец", value: commerce.legalName },
						{ label: "ИНН", value: commerce.inn },
						{ label: "Налоговый статус", value: commerce.taxStatus },
						{ label: "Адрес", value: commerce.address },
					]} />
					<p>
						Kolibri AI предоставляет удалённый доступ к программному сервису для подготовки смет,
						ведения проектов и формирования связанных документов. Конкретный состав доступа,
						срок и стоимость определяются выбранным тарифом из серверного каталога на момент заказа.
					</p>
				</LegalSection>
				<LegalSection title="2. Заказ и принятие условий">
					<p>
						Пользователь создаёт или использует учётную запись, выбирает опубликованный тариф и
						переходит на защищённую платёжную страницу Т‑Банка. Оплата выбранного заказа означает
						согласие с действующей редакцией оферты и условиями обработки данных.
					</p>
				</LegalSection>
				<LegalSection title="3. Цена и расчёты">
					<p>
						Цена показывается в рублях и поступает из серверного каталога биллинга. Kolibri не
						принимает реквизиты карты: платёжные данные вводятся на стороне банка. Повторно
						созданный или незавершённый запрос на оплату сам по себе не предоставляет доступ.
					</p>
				</LegalSection>
				<LegalSection title="4. Цифровая поставка">
					<p>
						Доступ активируется автоматически только после получения сервером подтверждённого
						статуса CONFIRMED от платёжного провайдера. Срок действия считается от момента
						активации и указывается в тарифе.
					</p>
				</LegalSection>
				<LegalSection title="5. Ограничения результата">
					<p>
						Сформированные расчёты и документы требуют проверки пользователем. Финальная цена
						строительных работ зависит от полноты исходных данных, региона, источников цен и
						фактических условий объекта.
					</p>
				</LegalSection>
				<LegalSection title="6. Обращения, отмена и возврат">
					<p>
						Запрос направляется продавцу по опубликованным контактам. Порядок рассмотрения,
						сведения, необходимые для идентификации платежа, и условия возврата приведены на
						странице «Оплата и возврат».
					</p>
				</LegalSection>
			</LegalPage>
		</PublicShell>
	);
}

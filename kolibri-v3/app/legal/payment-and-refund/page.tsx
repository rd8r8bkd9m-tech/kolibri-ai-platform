import type { Metadata } from "next";
import { LegalPage, LegalSection } from "@/components/public-site/legal/legal-page";
import { PublicShell } from "@/components/public-site/public-shell";
import { getPublicCommerceConfig } from "@/lib/server/public-commerce";

export const metadata: Metadata = { title: "Оплата, отмена и возврат" };
export const dynamic = "force-dynamic";

export default function PaymentAndRefundPage() {
	const commerce = getPublicCommerceConfig();
	return (
		<PublicShell commerce={commerce}>
			<LegalPage
				commerce={commerce}
				eyebrow="Условия заказа"
				title="Оплата, отмена и возврат"
				lead="Порядок оплаты цифрового доступа и действий при незавершённом или ошибочном платеже."
			>
				<LegalSection title="Оплата">
					<p>
						Стоимость и срок доступа показываются в карточке выбранного тарифа. После входа в
						учётную запись пользователь переходит на защищённую страницу Т‑Банка. Kolibri не
						сохраняет реквизиты банковской карты.
					</p>
				</LegalSection>
				<LegalSection title="Предоставление цифрового доступа">
					<p>
						Доступ не выдаётся по факту открытия платёжной формы, авторизации или возврата в
						приложение. Он активируется только после серверного уведомления банка со статусом
						CONFIRMED. При PENDING или UNKNOWN повторно оплачивать заказ не нужно — статус можно проверить в личном кабинете.
					</p>
				</LegalSection>
				<LegalSection title="Отмена незавершённого заказа">
					<p>
						Если платёж не подтверждён, пользователь может закрыть форму банка и не продолжать
						оплату. Неподтверждённый заказ не создаёт платный доступ.
					</p>
				</LegalSection>
				<LegalSection title="Запрос возврата">
					<p>
						Чтобы запросить возврат, напишите на {commerce.email ?? "адрес, который будет опубликован после настройки реквизитов"}.
						 Укажите почту учётной записи, дату, сумму и идентификатор платежа из личного кабинета.
						 Запрос рассматривается продавцом с учётом факта активации и использования цифрового доступа и применимых требований закона.
					</p>
				</LegalSection>
				<LegalSection title="Ошибочная или двойная оплата">
					<p>
						Не создавайте новый платёж, пока предыдущий имеет промежуточный статус. При двойном
						списании направьте оба идентификатора платежа продавцу. Статус возврата будет отражён в учётной записи после обработки банком.
					</p>
				</LegalSection>
			</LegalPage>
		</PublicShell>
	);
}

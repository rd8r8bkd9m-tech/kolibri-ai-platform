import Link from "next/link";
import {
	BookOpenText,
	CheckCircle2,
	ChevronRight,
	CircleAlert,
	CreditCard,
	KeyRound,
	Receipt,
	RefreshCcw,
	ShieldCheck,
	Wallet,
} from "lucide-react";
import { getPublicTbankConfig } from "@/lib/server/public-billing-config";
import { getPublicCommerceConfig } from "@/lib/server/public-commerce";
import { PublicPlanCatalog } from "../public-plan-catalog";

export function CommerceSection() {
	const payment = getPublicTbankConfig();
	const commerce = getPublicCommerceConfig();

	const requirements = [
		{
			label: "Реквизиты и контакты продавца",
			detail: commerce.ready
				? "Заполнены название, ИНН, адрес, e-mail и телефон"
				: `Не хватает: ${commerce.missing.join(", ")}`,
			ok: commerce.ready,
		},
		{
			label: "Оферта и правила возврата",
			detail: "Размещены в публичных страницах и доступны из сайта",
			ok: true,
		},
		{
			label: "Логотипы банка и платёжной системы",
			detail: "Оформлены в интерфейсе перед оплатой",
			ok: true,
		},
		{
			label: "Тестовый терминал",
			detail: "Сценарии `Общие` и `Формирование чека` пройдены",
			ok: ["demo", "test", "production"].includes(payment.status),
		},
	];

	return (
		<section className="kp-commerce kp-section" id="pricing" aria-labelledby="commerce-title">
			<div className="kp-container kp-commerce-grid">
				<div>
					<div className="kp-section-heading">
						<p className="kp-eyebrow"><span /> Тарифы и оплата</p>
						<h2 id="commerce-title">Один понятный тариф на старте.</h2>
						<p>
							Название, стоимость и срок доступа загружаются из серверного
							каталога биллинга. Оплата проходит на защищённой странице Т‑Банка.
						</p>
					</div>
					<div className="kp-commerce-points">
						<div><CreditCard /><p><strong>Оплата в Т‑Банке</strong><span>КолИ не получает данные банковской карты.</span></p></div>
						<div><KeyRound /><p><strong>Цифровой доступ</strong><span>Активируется после статуса CONFIRMED.</span></p></div>
						<div><RefreshCcw /><p><strong>Отмена и возврат</strong><span>Порядок обращения опубликован отдельной страницей.</span></p></div>
						<div><ShieldCheck /><p><strong>Серверный каталог</strong><span>Название, срок и цена тарифа приходят из биллинга.</span></p></div>
					</div>
					<div className="kp-commerce-gate">
						<p className={`kp-badge is-${payment.status}`}>{payment.label}</p>
						<h3>Как подключаем оплату по Т‑Банку</h3>
						<p className="kp-commerce-subtitle">
							Требования: публичная оферта и реквизиты, контактный блок,
							оформленный чеклист юридических требований и прохождение тестовых сценариев.
						</p>
						<div className="kp-commerce-actions" aria-label="Статус платёжной интеграции">
							<div>
								<p><BookOpenText aria-hidden="true" /> Режим интеграции</p>
								<strong>{payment.mode ? payment.mode.toUpperCase() : "OFF"}</strong>
							</div>
							<div>
								<p><Receipt aria-hidden="true" /> Квитанции</p>
								<strong>{payment.receiptMode ? payment.receiptMode : "disabled"}</strong>
							</div>
							<div>
								<p><Wallet aria-hidden="true" /> Готовность</p>
								<strong>{payment.providerReady ? "ок" : "проверка"}</strong>
							</div>
							<div>
								<p><ShieldCheck aria-hidden="true" /> Production</p>
								<strong>{payment.productionConfirmed ? "подтвержден" : "не подтверждён"}</strong>
							</div>
						</div>
						<details className="kp-commerce-details">
							<summary>
								Список обязательных шагов для активации <ChevronRight aria-hidden="true" />
							</summary>
							<div className="kp-commerce-compliance" aria-label="Проверка требований Т-Банка">
								{requirements.map((item) => (
									<div key={item.label} className={`kp-commerce-check ${item.ok ? "is-ok" : "is-warn"}`}>
										{item.ok ? (
											<CheckCircle2 aria-hidden="true" />
										) : (
											<CircleAlert aria-hidden="true" />
										)}
										<span>
											<strong>{item.label}</strong>
											<small>{item.detail}</small>
										</span>
									</div>
								))}
							</div>
							<ol>
								<li>Зарегистрировать/привязать магазин с типом <strong>Интернет-магазин</strong>.</li>
								<li>Заполнить контакты продавца и разместить оферту, возвраты, контакты в открытом виде.</li>
								<li>Разместить логотипы банка и платёжных систем на странице, пройти проверку содержимого.</li>
								<li>Включить тестовый терминал, выполнить сценарии в кабинете «Общие» и «Формирование чека».</li>
								<li>Получить рабочий терминал и перейти в статус «принимает платежи».</li>
							</ol>
						</details>
					</div>
					<Link className="kp-text-link" href="/legal/payment-and-refund">
						Условия оплаты, отмены и возврата →
					</Link>
				</div>
				<PublicPlanCatalog compact />
			</div>
		</section>
	);
}

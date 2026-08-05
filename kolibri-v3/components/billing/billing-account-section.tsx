"use client";

import {
	CalendarClock,
	CircleAlert,
	Clock3,
	CreditCard,
	LoaderCircle,
	Play,
	RefreshCw,
	ShieldCheck,
} from "lucide-react";
import { useState } from "react";
import { BillingPaymentState } from "@/components/billing/billing-payment-state";
import { BillingCheckoutOverlay } from "@/components/billing/billing-checkout-overlay";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type {
	BillingPlan,
	BillingSubscription,
} from "@/lib/billing/client";
import { useBillingAccount } from "@/lib/billing/use-billing-account";
import { cn } from "@/lib/utils";

const rubles = new Intl.NumberFormat("ru-RU", {
	style: "currency",
	currency: "RUB",
	maximumFractionDigits: 2,
});
const dates = new Intl.DateTimeFormat("ru-RU", {
	day: "numeric",
	month: "long",
	year: "numeric",
});

function countLabel(value: number, one: string, few: string, many: string) {
	const remainder100 = value % 100;
	const remainder10 = value % 10;
	if (remainder100 >= 11 && remainder100 <= 14) return many;
	if (remainder10 === 1) return one;
	if (remainder10 >= 2 && remainder10 <= 4) return few;
	return many;
}

function durationLabel(seconds: number) {
	if (seconds < 86_400) {
		const hours = Math.round(seconds / 3_600);
		return `${hours} ${countLabel(hours, "час", "часа", "часов")}`;
	}
	const days = Math.round(seconds / 86_400);
	return `${days} ${countLabel(days, "день", "дня", "дней")}`;
}

function dateLabel(timestamp: number) {
	return dates.format(new Date(timestamp * 1_000));
}

function SubscriptionCard({
	plan,
	subscription,
}: {
	plan?: BillingPlan;
	subscription: BillingSubscription;
}) {
	const scheduled = subscription.currentPeriodStart > Date.now() / 1_000;
	const periodCopy = scheduled
		? `Оплачено с ${dateLabel(subscription.currentPeriodStart)} до ${dateLabel(subscription.currentPeriodEnd)}.`
		: `Сметы и рабочие инструменты доступны до ${dateLabel(subscription.currentPeriodEnd)}.`;
	return (
		<div className="flex flex-col gap-4 px-5 py-4 min-[560px]:flex-row min-[560px]:items-center min-[560px]:justify-between">
			<div className="min-w-0">
				<div className="flex flex-wrap items-center gap-2">
					<p className="text-[14px] font-semibold">
						{plan?.name ?? "Доступ Kolibri"}
					</p>
					<span
						className={cn(
							"rounded-full border px-2 py-0.5 text-[10px] font-semibold",
							scheduled
								? "border-amber-500/35 bg-amber-500/[0.08] text-amber-700 dark:text-amber-300"
								: "border-emerald-600/30 bg-emerald-500/[0.07] text-emerald-700 dark:text-emerald-300",
						)}
					>
						{scheduled ? "Следующий период" : "Активен"}
					</span>
				</div>
				<p className="mt-1 text-[12px] leading-5 text-muted-foreground">
					{periodCopy}
				</p>
			</div>
			<div className="flex shrink-0 items-center gap-2 text-[12px] font-medium">
				<CalendarClock className="size-4 text-muted-foreground" aria-hidden="true" />
				<time
					dateTime={new Date(
						subscription.currentPeriodEnd * 1_000,
					).toISOString()}
				>
					{dateLabel(subscription.currentPeriodEnd)}
				</time>
			</div>
		</div>
	);
}

function PlanCard({
	busy,
	disabled,
	onBuy,
	plan,
}: {
	busy: boolean;
	disabled: boolean;
	onBuy: () => void;
	plan: BillingPlan;
}) {
	return (
		<article className="flex min-h-56 flex-col rounded-2xl border bg-card p-5 shadow-[0_10px_30px_rgb(15_23_42_/_0.04)]">
			<div>
				<p className="text-[15px] font-semibold">{plan.name}</p>
				<p className="mt-3 text-3xl font-semibold tracking-[-0.035em]">
					{rubles.format(plan.amountMinor / 100)}
				</p>
				<p className="mt-1 text-[12px] text-muted-foreground">
					Разовая оплата на {durationLabel(plan.durationSeconds)}
				</p>
			</div>
			<div className="mt-auto pt-6">
				<Button
					type="button"
					disabled={disabled}
					onClick={onBuy}
					className="min-h-11 w-full rounded-xl"
				>
					{busy ? (
						<LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
					) : (
						<CreditCard className="size-4" aria-hidden="true" />
					)}
					Оплатить
				</Button>
				<p className="mt-3 text-center text-[10px] leading-4 text-muted-foreground">
					Оплата откроется на защищённой странице Т‑Банка.
					Данные карты не передаются Kolibri.
				</p>
			</div>
		</article>
	);
}

function RuntimeCheckCard({
	busy,
	disabled,
	onRun,
	plan,
}: {
	busy: boolean;
	disabled: boolean;
	onRun: () => void;
	plan: BillingPlan;
}) {
	return (
		<article className="flex min-h-40 flex-col rounded-2xl border bg-card p-5 shadow-[0_10px_30px_rgb(15_23_42_/_0.04)]">
			<div>
				<p className="text-[14px] font-semibold">Runtime-check оплаты</p>
				<p className="mt-2 text-[12px] text-muted-foreground">
					Короткий проход: создаём intent по тарифу «{plan.name}», открываем
					платежную страницу T‑Банка и после возврата проверяем `paymentUrl`
					и статус в том же чате кабинета.
				</p>
			</div>
			<div className="mt-auto pt-6">
				<Button
					type="button"
					disabled={disabled}
					onClick={onRun}
					variant="outline"
					className="min-h-11 w-full rounded-xl"
				>
					{busy ? (
						<LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
					) : (
						<Play className="size-4" aria-hidden="true" />
					)}
					Запустить runtime-check в один проход
				</Button>
				<p className="mt-3 text-center text-[10px] leading-4 text-muted-foreground">
					После возврата статус оплаченного intent появляется в блоке ниже.
				</p>
			</div>
		</article>
	);
}

export function BillingAccountSection() {
	const account = useBillingAccount();
	const [checkoutUrl, setCheckoutUrl] = useState<string | null>(null);
	const paidSubscriptions = account.subscriptions.filter(
		(subscription) =>
			subscription.status === "active" &&
			subscription.currentPeriodEnd > Date.now() / 1_000,
	);

	const startPlanPayment = async (planCode: string) => {
		const nextPaymentUrl = await account.beginPayment(planCode);
		if (nextPaymentUrl) setCheckoutUrl(nextPaymentUrl);
	};

	const continuePayment = () => {
		const nextPaymentUrl = account.continuePayment();
		if (nextPaymentUrl) setCheckoutUrl(nextPaymentUrl);
	};

	return (
		<section data-slot="billing-account-section">
			<div data-slot="settings-section-heading">
				<div className="flex items-center gap-2.5">
					<CreditCard className="size-5 text-muted-foreground" aria-hidden="true" />
					<h2 className="text-2xl font-semibold tracking-[-0.025em]">
						Использование и оплата
					</h2>
				</div>
				<p className="mt-2 max-w-2xl text-[13px] leading-5 text-muted-foreground">
					Текущий доступ и разовые платежи без автоматического продления.
				</p>
			</div>

				<BillingPaymentState
					checking={account.checkingPayment}
					error={account.paymentError}
					onContinue={continuePayment}
					onRefresh={account.refreshPayment}
					payment={account.payment}
				/>
				{account.plans.length > 0 ? (
					<RuntimeCheckCard
						busy={Boolean(account.creatingPlan)}
						disabled={account.creatingPlan !== null}
						plan={account.plans[0]}
						onRun={() => void startPlanPayment(account.plans[0].code)}
					/>
				) : null}

			{account.loading ? (
				<div
					className="mt-8 space-y-6"
					aria-label="Загружаем данные оплаты"
					role="status"
				>
					<Skeleton className="h-28 w-full rounded-2xl" />
					<Skeleton className="h-56 w-full rounded-2xl" />
				</div>
			) : account.loadError ? (
				<div
					className="mt-8 rounded-2xl border border-destructive/25 bg-destructive/[0.04] p-5"
					role="alert"
				>
					<div className="flex items-start gap-3">
						<CircleAlert
							className="mt-0.5 size-5 text-destructive"
							aria-hidden="true"
						/>
						<div>
							<p className="text-[14px] font-semibold">
								Не удалось загрузить оплату
							</p>
							<p className="mt-1 text-[12px] leading-5 text-muted-foreground">
								{account.loadError}
							</p>
						</div>
					</div>
					<Button
						type="button"
						variant="outline"
						size="sm"
						onClick={account.refreshAccount}
						className="mt-4 min-h-10 rounded-lg bg-background shadow-none"
					>
						<RefreshCw className="size-4" aria-hidden="true" />
						Повторить
					</Button>
				</div>
			) : (
				<>
					<section className="mt-8">
						<h3 className="mb-3 text-[15px] font-semibold">
							Текущий доступ
						</h3>
						<div className="divide-y overflow-hidden rounded-2xl border bg-card">
							{paidSubscriptions.length > 0 ? (
								paidSubscriptions.map((subscription) => (
									<SubscriptionCard
										key={subscription.id}
										subscription={subscription}
										plan={account.plans.find(
											(plan) => plan.code === subscription.planCode,
										)}
									/>
								))
							) : (
								<div className="flex items-start gap-3 px-5 py-4">
									<Clock3
										className="mt-0.5 size-5 text-muted-foreground"
										aria-hidden="true"
									/>
									<div>
										<p className="text-[14px] font-medium">
											Нет активного оплаченного периода
										</p>
										<p className="mt-1 text-[12px] leading-5 text-muted-foreground">
											Доступ изменится только после подтверждённой оплаты.
										</p>
									</div>
								</div>
							)}
						</div>
					</section>

					<section className="mt-8">
						<h3 className="mb-3 text-[15px] font-semibold">Тарифы</h3>
						{account.plans.length > 0 ? (
							<div className="grid grid-cols-1 gap-3 min-[640px]:grid-cols-2">
								{account.plans.map((plan) => (
									<PlanCard
										key={plan.code}
										plan={plan}
										busy={account.creatingPlan === plan.code}
										disabled={account.creatingPlan !== null}
										onBuy={() => void startPlanPayment(plan.code)}
									/>
								))}
							</div>
						) : (
							<div className="flex min-h-48 flex-col items-center justify-center rounded-2xl border border-dashed bg-muted/15 px-6 text-center">
								<span className="flex size-11 items-center justify-center rounded-2xl bg-muted">
									<ShieldCheck
										className="size-5 text-muted-foreground"
										aria-hidden="true"
									/>
								</span>
								<p className="mt-4 text-sm font-semibold">
									Тариф готовится к публикации
								</p>
								<p className="mt-1 max-w-md text-[12px] leading-5 text-muted-foreground">
									Серверный каталог тарифов временно недоступен.
								</p>
								<p className="mt-1 max-w-md text-[12px] leading-5 text-muted-foreground">
									Цена не подставляется вручную и появится только из каталога биллинга.
								</p>
							</div>
				)}
			</section>
		</>
			)}
			{checkoutUrl ? (
				<BillingCheckoutOverlay
					open
					paymentUrl={checkoutUrl}
					onClose={() => setCheckoutUrl(null)}
				/>
			) : null}
		</section>
	);
}

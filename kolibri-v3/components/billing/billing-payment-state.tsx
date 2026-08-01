"use client";

import {
	CheckCircle2,
	CircleAlert,
	Clock3,
	ExternalLink,
	RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type { BillingPaymentIntent } from "@/lib/billing/client";
import { cn } from "@/lib/utils";

const FAILED_STATUSES = new Set(["failed", "canceled", "refunded"]);
const TERMINAL_STATUSES = new Set([
	"succeeded",
	"failed",
	"canceled",
	"partially_refunded",
	"refunded",
]);

function paymentCopy(payment: BillingPaymentIntent | null) {
	switch (payment?.status) {
		case "succeeded":
			return {
				title: "Оплата подтверждена",
				description:
					"Доступ активирован по подтверждённому уведомлению банка.",
			};
		case "authorized":
			return {
				title: "Платёж авторизован",
				description:
					"Страница обновит статус автоматически. Повторно платить не нужно.",
			};
		case "partially_refunded":
			return {
				title: "Часть платежа возвращена",
				description:
					"Оплаченный период сохраняется; детали возврата доступны в банковской операции.",
			};
		case "refunded":
			return {
				title: "Платёж возвращён",
				description:
					"Доступ по этому платежу закрыт после полного возврата.",
			};
		case "canceled":
			return {
				title: "Платёж отменён",
				description:
					"Доступ не изменён. Новый платёж можно начать из карточки тарифа.",
			};
		case "failed":
			return {
				title: "Платёж отклонён",
				description:
					"Доступ не изменён. Новый платёж можно начать из карточки тарифа.",
			};
		case "initializing":
		case "pending":
		case "unknown":
			return {
				title: "Ожидаем подтверждение банка",
				description:
					"Страница обновит статус автоматически. Повторно платить не нужно.",
			};
		default:
			return {
				title: "Оплата не завершена",
				description: "Сервис оплаты требует повторной проверки.",
			};
	}
}

export function BillingPaymentState({
	checking,
	error,
	onContinue,
	onRefresh,
	payment,
}: {
	checking: boolean;
	error: string | null;
	onContinue: () => void;
	onRefresh: () => void;
	payment: BillingPaymentIntent | null;
}) {
	if (!payment && !error) return null;
	const succeeded = payment?.status === "succeeded";
	const failed = !payment || FAILED_STATUSES.has(payment.status);
	const terminal = !payment || TERMINAL_STATUSES.has(payment.status);
	const copy = paymentCopy(payment);
	const description = error ?? copy.description;
	const Icon = succeeded ? CheckCircle2 : failed ? CircleAlert : Clock3;

	return (
		<div
			className={cn(
				"mt-6 rounded-2xl border p-4",
				succeeded &&
					"border-emerald-600/25 bg-emerald-500/[0.06] text-emerald-950 dark:text-emerald-100",
				failed && "border-destructive/25 bg-destructive/[0.05]",
				!succeeded && !failed &&
					"border-amber-500/30 bg-amber-500/[0.07]",
			)}
			role={failed || error ? "alert" : "status"}
		>
			<div className="flex items-start gap-3">
				<Icon className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
				<div className="min-w-0 flex-1">
					<p className="text-[14px] font-semibold">{copy.title}</p>
					<p className="mt-1 text-[12px] leading-5 text-current/75">
						{description}
					</p>
					{payment ? (
						<p className="mt-1 font-mono text-[10px] text-current/55">
							Платёж · {payment.id.slice(-8)}
						</p>
					) : null}
				</div>
			</div>
			{!terminal ? (
				<div className="mt-3 flex flex-wrap gap-2 pl-8">
					{payment?.paymentUrl && payment.status === "pending" ? (
						<Button
							type="button"
							size="sm"
							onClick={onContinue}
							className="min-h-10 rounded-lg"
						>
							Продолжить оплату
							<ExternalLink className="size-4" aria-hidden="true" />
						</Button>
					) : null}
					{payment ? (
						<Button
							type="button"
							variant="outline"
							size="sm"
							disabled={checking}
							onClick={onRefresh}
							className="min-h-10 rounded-lg bg-background shadow-none"
						>
							<RefreshCw
								className={cn("size-4", checking && "animate-spin")}
								aria-hidden="true"
							/>
							Проверить статус
						</Button>
					) : null}
				</div>
			) : null}
		</div>
	);
}

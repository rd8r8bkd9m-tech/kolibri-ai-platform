import {
	ActivityIndicator,
	Pressable,
	StyleSheet,
	Text,
	View,
} from "react-native";
import { SettingsGroup } from "@/components/settings/settings-group";
import {
	FontSize,
	FontWeight,
	LetterSpacing,
	LineHeight,
	Radius,
	Spacing,
} from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import type { BillingPaymentIntent, BillingPlan } from "@/src/billing/client";
import { useWebBillingAccount } from "@/src/billing/use-web-billing-account";
export type WebBillingSettingsProps = {
	authorizedFetch: typeof fetch;
	refreshProfile: () => Promise<unknown>;
	returnedIntent?: string;
};
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
const countLabel = (value: number, one: string, few: string, many: string) => {
	const remainder100 = value % 100;
	const remainder10 = value % 10;
	if (remainder100 >= 11 && remainder100 <= 14) return many;
	if (remainder10 === 1) return one;
	if (remainder10 >= 2 && remainder10 <= 4) return few;
	return many;
};
const durationLabel = (seconds: number) => {
	if (seconds < 86_400) {
		const hours = Math.round(seconds / 3_600);
		return `${hours} ${countLabel(hours, "час", "часа", "часов")}`;
	}
	const days = Math.round(seconds / 86_400);
	return `${days} ${countLabel(days, "день", "дня", "дней")}`;
};
const paymentCopy = (payment: BillingPaymentIntent | null) => {
	switch (payment?.status) {
		case "succeeded":
			return ["Оплата подтверждена", "Доступ активирован банком.", "success"] as const;
		case "authorized":
			return ["Платёж авторизован", "Ждём окончательное подтверждение банка.", "pending"] as const;
		case "partially_refunded":
			return ["Часть платежа возвращена", "Оплаченный период сохраняется.", "pending"] as const;
		case "refunded":
			return ["Платёж возвращён", "Доступ по этому платежу закрыт.", "error"] as const;
		case "failed":
		case "canceled":
			return ["Оплата не завершена", "Доступ не изменён.", "error"] as const;
		default:
			return ["Проверяем оплату", "Повторно платить не нужно.", "pending"] as const;
	}
};
function PaymentState({
	account,
}: {
	account: ReturnType<typeof useWebBillingAccount>;
}) {
	const { colors } = useTheme();
	if (!account.payment && !account.paymentError) return null;
	const [title, fallback, tone] = paymentCopy(account.payment);
	const terminal = new Set([
		"succeeded",
		"failed",
		"canceled",
		"partially_refunded",
		"refunded",
	]).has(account.payment?.status ?? "");
	const toneColor =
		tone === "success"
			? colors.success
			: tone === "error"
				? colors.destructive
				: colors.foreground;
	return (
		<SettingsGroup title="Статус платежа">
			<View accessibilityLiveRegion="polite" style={styles.statusBody}>
				<View style={[styles.statusMark, { backgroundColor: toneColor }]} />
				<View style={styles.flex}>
					<Text style={[styles.itemTitle, { color: colors.foreground }]}>{title}</Text>
					<Text style={[styles.bodyCopy, { color: colors.mutedForeground }]}>
						{account.paymentError ?? fallback}
					</Text>
					{account.payment ? (
						<Text style={[styles.reference, { color: colors.mutedForeground }]}>
							Платёж · {account.payment.id.slice(-8)}
						</Text>
					) : null}
					{!terminal ? (
						<View style={styles.inlineActions}>
							{account.payment?.paymentUrl && account.payment.status === "pending" ? (
								<ActionButton label="Продолжить оплату" onPress={account.continuePayment} />
							) : null}
							<ActionButton
								disabled={account.checkingPayment}
								label={account.checkingPayment ? "Проверяем…" : "Проверить статус"}
								onPress={account.refreshPayment}
								secondary
							/>
						</View>
					) : null}
				</View>
			</View>
		</SettingsGroup>
	);
}
function ActionButton({
	disabled = false,
	label,
	onPress,
	secondary = false,
}: {
	disabled?: boolean;
	label: string;
	onPress: () => void;
	secondary?: boolean;
}) {
	const { colors } = useTheme();
	return (
		<Pressable
			accessibilityRole="button"
			disabled={disabled}
			onPress={onPress}
			style={({ pressed }) => [
				styles.action,
				{
					backgroundColor: secondary ? colors.muted : colors.primary,
					borderColor: secondary ? colors.border : colors.primary,
				},
				pressed && styles.pressed,
				disabled && styles.disabled,
			]}
		>
			<Text
				style={[
					styles.actionLabel,
					{ color: secondary ? colors.foreground : colors.primaryForeground },
				]}
			>
				{label}
			</Text>
		</Pressable>
	);
}
function PlanRow({
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
	const { colors } = useTheme();
	return (
		<View style={[styles.plan, { borderBottomColor: colors.border }]}>
			<View style={styles.planHeading}>
				<View style={styles.flex}>
					<Text style={[styles.itemTitle, { color: colors.foreground }]}>{plan.name}</Text>
					<Text style={[styles.bodyCopy, { color: colors.mutedForeground }]}>
						Разовая оплата на {durationLabel(plan.durationSeconds)}
					</Text>
				</View>
				<Text style={[styles.price, { color: colors.foreground }]}>
					{rubles.format(plan.amountMinor / 100)}
				</Text>
			</View>
			<ActionButton
				disabled={disabled}
				label={busy ? "Открываем…" : "Перейти к оплате"}
				onPress={onBuy}
			/>
		</View>
	);
}
export function WebBillingSettings({
	authorizedFetch,
	refreshProfile,
	returnedIntent,
}: WebBillingSettingsProps) {
	const { colors } = useTheme();
	const account = useWebBillingAccount({
		authorizedFetch,
		onEntitlementChanged: refreshProfile,
		returnedIntent,
	});
	const activeSubscriptions = account.subscriptions.filter(
		(subscription) => subscription.status === "active",
	);
	return (
		<>
			<PaymentState account={account} />
			{account.loading ? (
				<SettingsGroup title="Оплата и тариф">
					<View accessibilityLabel="Загружаем данные оплаты" style={styles.loading}>
						<ActivityIndicator color={colors.foreground} />
						<Text style={[styles.bodyCopy, { color: colors.mutedForeground }]}>Загружаем…</Text>
					</View>
				</SettingsGroup>
			) : account.loadError ? (
				<SettingsGroup title="Оплата и тариф">
					<View accessibilityRole="alert" style={styles.messageBody}>
						<Text style={[styles.itemTitle, { color: colors.foreground }]}>Не удалось загрузить оплату</Text>
						<Text style={[styles.bodyCopy, { color: colors.mutedForeground }]}>{account.loadError}</Text>
						<View style={styles.compactAction}>
							<ActionButton label="Повторить" onPress={account.refreshAccount} secondary />
						</View>
					</View>
				</SettingsGroup>
			) : (
				<>
					<SettingsGroup title="Текущий доступ">
						<View style={styles.messageBody}>
							{activeSubscriptions.length ? (
								activeSubscriptions.map((subscription) => {
									const plan = account.plans.find((item) => item.code === subscription.planCode);
									return (
										<View key={subscription.id} style={styles.subscription}>
											<Text style={[styles.itemTitle, { color: colors.foreground }]}>{plan?.name ?? "Доступ Kolibri"}</Text>
											<Text style={[styles.bodyCopy, { color: colors.mutedForeground }]}>Доступ активен до {dates.format(new Date(subscription.currentPeriodEnd * 1_000))}.</Text>
										</View>
									);
								})
							) : (
								<>
									<Text style={[styles.itemTitle, { color: colors.foreground }]}>Нет активного оплаченного периода</Text>
									<Text style={[styles.bodyCopy, { color: colors.mutedForeground }]}>Доступ изменится только после подтверждённой оплаты.</Text>
								</>
							)}
						</View>
					</SettingsGroup>
					<SettingsGroup
						footer={
							<Text style={[styles.footer, { color: colors.mutedForeground }]}>
								Разовая оплата без автоматического продления. Защищённая страница откроется в Т‑Банке: карта, СБП (QR) или T‑Pay; реквизиты не передаются Kolibri.
							</Text>
						}
						title="Тарифы"
					>
						{account.plans.length ? (
							account.plans.map((plan) => (
								<PlanRow
									busy={account.creatingPlan === plan.code}
									disabled={account.creatingPlan !== null}
									key={plan.code}
									onBuy={() => void account.beginPayment(plan.code)}
									plan={plan}
								/>
							))
						) : (
							<View style={styles.emptyBody}>
								<Text style={[styles.itemTitle, { color: colors.foreground }]}>Оплата пока не подключена</Text>
								<Text style={[styles.bodyCopy, { color: colors.mutedForeground }]}>Тарифы появятся после публикации подтверждённых условий.</Text>
							</View>
						)}
					</SettingsGroup>
					<SettingsGroup title="История платежей">
						{account.payments.length ? (
							account.payments.map((payment) => (
								<View
									key={payment.id}
									style={[styles.paymentRow, { borderTopColor: colors.border }]}
								>
									<View style={styles.flex}>
										<Text style={[styles.itemTitle, { color: colors.foreground }]}>
											{payment.planName}
										</Text>
										<Text style={[styles.bodyCopy, { color: colors.mutedForeground }]}>
											{dates.format(new Date(payment.createdAt * 1_000))} · {payment.id.slice(-8)}
										</Text>
									</View>
									<View style={styles.paymentAmount}>
										<Text style={[styles.price, { color: colors.foreground }]}>
											{rubles.format(payment.amountMinor / 100)}
										</Text>
										<Text style={[styles.bodyCopy, { color: colors.mutedForeground }]}>
											{payment.status}
										</Text>
									</View>
								</View>
							))
						) : (
							<View style={styles.emptyBody}>
								<Text style={[styles.bodyCopy, { color: colors.mutedForeground }]}>
									Платежей пока нет.
								</Text>
							</View>
						)}
					</SettingsGroup>
				</>
			)}
		</>
	);
}
const styles = StyleSheet.create({
	flex: { flex: 1 },
	loading: {
		alignItems: "center",
		flexDirection: "row",
		gap: Spacing.md,
		minHeight: 72,
		paddingHorizontal: Spacing.lg,
	},
	messageBody: {
		gap: Spacing.xs,
		paddingHorizontal: Spacing.lg,
		paddingVertical: Spacing.lg,
	},
	emptyBody: {
		alignItems: "center",
		gap: Spacing.sm,
		minHeight: 130,
		justifyContent: "center",
		padding: Spacing.xl,
	},
	statusBody: { flexDirection: "row", gap: Spacing.md, padding: Spacing.lg },
	statusMark: {
		borderRadius: Radius.xs,
		height: 10,
		marginTop: Spacing.xs,
		width: 10,
	},
	itemTitle: {
		fontSize: FontSize.medium,
		fontWeight: FontWeight.semibold,
		lineHeight: LineHeight.normal,
	},
	bodyCopy: { fontSize: FontSize.footnote, lineHeight: LineHeight.small },
	reference: {
		fontFamily: "monospace",
		fontSize: FontSize.caption2,
		lineHeight: LineHeight.footnote,
	},
	inlineActions: {
		flexDirection: "row",
		flexWrap: "wrap",
		gap: Spacing.sm,
		marginTop: Spacing.md,
	},
	action: {
		alignItems: "center",
		borderRadius: Radius.md,
		borderWidth: 1,
		justifyContent: "center",
		minHeight: 42,
		paddingHorizontal: Spacing.lg,
	},
	actionLabel: {
		fontSize: FontSize.small,
		fontWeight: FontWeight.semibold,
		lineHeight: LineHeight.compact,
	},
	pressed: { opacity: 0.68 },
	disabled: { opacity: 0.45 },
	compactAction: { alignSelf: "flex-start", marginTop: Spacing.sm },
	plan: {
		borderBottomWidth: StyleSheet.hairlineWidth,
		gap: Spacing.lg,
		padding: Spacing.lg,
	},
	planHeading: {
		alignItems: "flex-start",
		flexDirection: "row",
		gap: Spacing.md,
	},
	price: {
		fontSize: FontSize.title,
		fontWeight: FontWeight.bold,
		letterSpacing: LetterSpacing.base,
		lineHeight: LineHeight.relaxed,
	},
	subscription: { gap: Spacing.xs },
	footer: { fontSize: FontSize.caption2, lineHeight: LineHeight.footnote },
	paymentRow: {
		alignItems: "center",
		borderTopWidth: StyleSheet.hairlineWidth,
		flexDirection: "row",
		gap: Spacing.md,
		paddingHorizontal: Spacing.lg,
		paddingVertical: Spacing.md,
	},
	paymentAmount: { alignItems: "flex-end" },
});

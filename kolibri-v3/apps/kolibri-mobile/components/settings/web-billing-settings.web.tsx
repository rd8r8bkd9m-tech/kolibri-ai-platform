import {
	ActivityIndicator,
	Pressable,
	StyleSheet,
	Text,
	View,
} from "react-native";
import { SettingsGroup } from "@/components/settings/settings-group";
import { Radius } from "@/constants/theme";
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
								Разовая оплата без автоматического продления. Защищённая страница откроется в Т‑Банке; реквизиты карты не передаются Kolibri.
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
				</>
			)}
		</>
	);
}
const styles = StyleSheet.create({
	flex: { flex: 1 },
	loading: { alignItems: "center", flexDirection: "row", gap: 10, minHeight: 72, paddingHorizontal: 16 },
	messageBody: { gap: 5, paddingHorizontal: 16, paddingVertical: 15 },
	emptyBody: { alignItems: "center", gap: 6, minHeight: 130, justifyContent: "center", padding: 20 },
	statusBody: { flexDirection: "row", gap: 12, padding: 16 },
	statusMark: { borderRadius: 5, height: 10, marginTop: 5, width: 10 },
	itemTitle: { fontSize: 15, fontWeight: "600", lineHeight: 20 },
	bodyCopy: { fontSize: 13, lineHeight: 19 },
	reference: { fontFamily: "monospace", fontSize: 11, lineHeight: 17 },
	inlineActions: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 10 },
	action: { alignItems: "center", borderRadius: Radius.md, borderWidth: 1, justifyContent: "center", minHeight: 42, paddingHorizontal: 15 },
	actionLabel: { fontSize: 14, fontWeight: "600", lineHeight: 18 },
	pressed: { opacity: 0.68 },
	disabled: { opacity: 0.45 },
	compactAction: { alignSelf: "flex-start", marginTop: 8 },
	plan: { borderBottomWidth: StyleSheet.hairlineWidth, gap: 14, padding: 16 },
	planHeading: { alignItems: "flex-start", flexDirection: "row", gap: 12 },
	price: { fontSize: 18, fontWeight: "700", letterSpacing: -0.3, lineHeight: 23 },
	subscription: { gap: 4 },
	footer: { fontSize: 11, lineHeight: 17 },
});

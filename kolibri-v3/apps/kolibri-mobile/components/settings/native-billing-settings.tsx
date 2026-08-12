import * as Linking from "expo-linking";
import { useCallback, useEffect, useRef, useState } from "react";
import {
	ActivityIndicator,
	Pressable,
	StyleSheet,
	Switch,
	Text,
	View,
} from "react-native";

import { SettingsGroup } from "@/components/settings/settings-group";
import { Icon } from "@/components/ui/icon";
import { Radius } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";
import {
	type BillingPlan,
	type BillingSubscription,
	createWebBillingIdempotencyKey,
	createWebBillingPayment,
	getWebBillingPlans,
	getWebBillingPayment,
	getWebBillingSubscriptions,
	setWebBillingAutoRenew,
} from "@/src/billing/client";
import { useMobileSession } from "@/src/auth/mobile-session";

const TERMINAL_PAYMENT_STATUSES = new Set([
	"succeeded",
	"failed",
	"canceled",
	"partially_refunded",
	"refunded",
]);
const MAX_POLL_ATTEMPTS = 100;

const formatMoney = (amountMinor: number) =>
	new Intl.NumberFormat("ru-RU", {
		currency: "RUB",
		maximumFractionDigits: 2,
		style: "currency",
	}).format(amountMinor / 100);

const formatPeriodEnd = (epochSeconds: number) =>
	new Intl.DateTimeFormat("ru-RU", {
		day: "numeric",
		month: "long",
		year: "numeric",
	}).format(new Date(epochSeconds * 1_000));

const STATUS_LABEL: Record<BillingSubscription["status"], string> = {
	active: "Активна",
	refunded: "Возвращена",
	canceled: "Отменена",
	expired: "Истекла",
};

export function NativeBillingSettings() {
	const session = useMobileSession();
	const { colors } = useTheme();
	const [plans, setPlans] = useState<readonly BillingPlan[]>([]);
	const [subscriptions, setSubscriptions] = useState<
		readonly BillingSubscription[]
	>([]);
	const [status, setStatus] = useState<"loading" | "ready" | "error">(
		"loading",
	);
	const [message, setMessage] = useState("");
	const [checkoutPlan, setCheckoutPlan] = useState<string | null>(null);
	const [polling, setPolling] = useState(false);
	const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
	const pollAttemptsRef = useRef(0);

	const load = useCallback(async () => {
		setStatus("loading");
		setMessage("");
		try {
			const [nextPlans, nextSubscriptions] = await Promise.all([
				getWebBillingPlans(session.authorizedFetch),
				getWebBillingSubscriptions(session.authorizedFetch),
			]);
			setPlans(nextPlans);
			setSubscriptions(nextSubscriptions);
			setStatus("ready");
		} catch (reason) {
			setMessage(
				reason instanceof Error
					? reason.message
					: "Не удалось загрузить тарифы.",
			);
			setStatus("error");
		}
	}, [session.authorizedFetch]);

	useEffect(() => {
		const timer = setTimeout(() => void load(), 0);
		return () => {
			clearTimeout(timer);
			if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
		};
	}, [load]);

	const activeSubscription = subscriptions.find(
		(subscription) => subscription.status === "active",
	);

	const startCheckout = async (plan: BillingPlan) => {
		if (checkoutPlan) return;
		haptics.selection();
		setCheckoutPlan(plan.code);
		setPolling(true);
		setMessage("");
		try {
			const payment = await createWebBillingPayment(
				session.authorizedFetch,
				plan.code,
				createWebBillingIdempotencyKey(),
			);
			if (!payment.paymentUrl) {
				throw new Error("Платёжная ссылка не получена.");
			}
			pollAttemptsRef.current = 0;
			await Linking.openURL(payment.paymentUrl);
			// The bank app/browser owns the flow now; poll the server until the
			// exact intent reaches a terminal state. A pre-existing active
			// subscription must never count as success for this checkout.
			pollForPayment(payment.id);
		} catch (reason) {
			stopPolling(
				reason instanceof Error ? reason.message : "Не удалось начать оплату.",
			);
			haptics.error();
		}
	};

	const stopPolling = (message?: string) => {
		if (pollTimerRef.current) {
			clearTimeout(pollTimerRef.current);
			pollTimerRef.current = null;
		}
		setPolling(false);
		setCheckoutPlan(null);
		if (message) setMessage(message);
	};

	const pollForPayment = (intentId: string) => {
		const attempt = async () => {
			pollAttemptsRef.current += 1;
			try {
				const payment = await getWebBillingPayment(
					session.authorizedFetch,
					intentId,
				);
				if (TERMINAL_PAYMENT_STATUSES.has(payment.status)) {
					if (payment.status === "succeeded") {
						const next = await getWebBillingSubscriptions(
							session.authorizedFetch,
						);
						setSubscriptions(next);
						const activated = next.some(
							(subscription) =>
								subscription.paymentIntentId === intentId &&
								subscription.status === "active",
						);
						stopPolling(
							activated
								? undefined
								: "Оплата подтверждена, доступ активируется. Обновите раздел через несколько секунд.",
						);
						if (activated) {
							haptics.success();
							await session.refreshProfile();
						}
					} else {
						stopPolling("Оплата не завершена. Доступ не изменён.");
						haptics.error();
					}
					return;
				}
				if (pollAttemptsRef.current >= MAX_POLL_ATTEMPTS) {
					stopPolling(
						"Банк не подтвердил оплату вовремя. Проверьте статус в разделе оплаты.",
					);
					return;
				}
				pollTimerRef.current = setTimeout(attempt, 3_000);
			} catch {
				// keep polling; the provider may be mid-redirect
				if (pollAttemptsRef.current >= MAX_POLL_ATTEMPTS) {
					stopPolling(
						"Не удалось проверить оплату. Проверьте статус в разделе оплаты.",
					);
					return;
				}
				pollTimerRef.current = setTimeout(attempt, 3_000);
			}
		};
		void attempt();
	};

	const toggleAutoRenew = async (subscription: BillingSubscription) => {
		haptics.selection();
		setMessage("");
		try {
			const next = await setWebBillingAutoRenew(
				session.authorizedFetch,
				subscription.id,
				!subscription.autoRenew,
			);
			setSubscriptions((current) =>
				current.map((entry) =>
					entry.id === next.id ? next : entry,
				),
			);
			haptics.success();
		} catch (reason) {
			setMessage(
				reason instanceof Error
					? reason.message
					: "Не удалось изменить автопродление.",
			);
			haptics.error();
		}
	};

	const refunded = subscriptions.find(
		(subscription) => subscription.status === "refunded",
	);

	if (status === "loading") {
		return (
			<View accessibilityLabel="Загрузка тарифов" style={styles.center}>
				<ActivityIndicator color={colors.foreground} />
			</View>
		);
	}

	if (status === "error") {
		return (
			<View style={styles.center}>
				<Text
					accessibilityRole="alert"
					style={[styles.errorText, { color: colors.destructive }]}
				>
					{message}
				</Text>
				<Pressable
					accessibilityRole="button"
					onPress={() => void load()}
					style={[styles.retry, { backgroundColor: colors.surface }]}
				>
					<Icon name="reload" size={17} color={colors.foreground} />
					<Text style={[styles.retryText, { color: colors.foreground }]}>
						Повторить
					</Text>
				</Pressable>
			</View>
		);
	}

	return (
		<>
			<SettingsGroup title="Текущий доступ">
				{activeSubscription ? (
					<View
						style={[styles.subscriptionCard, { backgroundColor: colors.surface }]}
					>
						<View style={styles.subscriptionHeader}>
							<View>
								<Text style={[styles.subscriptionTitle, { color: colors.foreground }]}>
									{activeSubscription.planCode}
								</Text>
								<Text style={[styles.subscriptionMeta, { color: colors.mutedForeground }]}>
									{STATUS_LABEL[activeSubscription.status]} · до{" "}
									{formatPeriodEnd(activeSubscription.currentPeriodEnd)}
								</Text>
							</View>
							<View
								style={[styles.statusBadge, { backgroundColor: colors.muted }]}
							>
								<Text style={[styles.statusBadgeText, { color: colors.success }]}>
									Активна
								</Text>
							</View>
						</View>
						<View
							style={[
								styles.autoRenewRow,
								{ borderTopColor: colors.border },
							]}
						>
							<View style={styles.autoRenewCopy}>
								<Text style={[styles.autoRenewTitle, { color: colors.foreground }]}>
									Автопродление
								</Text>
								<Text style={[styles.autoRenewHint, { color: colors.mutedForeground }]}>
									{activeSubscription.rebillConfigured
										? "Списание по сохранённой карте"
										: "Карта ещё не привязана"}
								</Text>
							</View>
							<Switch
								accessibilityLabel="Автопродление подписки"
								onValueChange={() => void toggleAutoRenew(activeSubscription)}
								value={activeSubscription.autoRenew}
							/>
						</View>
					</View>
				) : refunded ? (
					<View style={styles.center}>
						<Text style={[styles.errorText, { color: colors.mutedForeground }]}>
							Подписка возвращена. Оплатите тариф заново, чтобы продолжить.
						</Text>
					</View>
				) : (
					<View style={styles.center}>
						<Text style={[styles.emptyText, { color: colors.mutedForeground }]}>
							Нет активного оплаченного периода. Доступ изменится только после
							подтверждённой оплаты.
						</Text>
					</View>
				)}
			</SettingsGroup>

			<SettingsGroup title="Тарифы">
				{plans.map((plan) => {
					const active = activeSubscription?.planCode === plan.code;
					const busy = checkoutPlan === plan.code;
					return (
						<View
							key={plan.code}
							style={[styles.planCard, { backgroundColor: colors.surface }]}
						>
							<View style={styles.planCopy}>
								<Text style={[styles.planName, { color: colors.foreground }]}>
									{plan.name}
								</Text>
								<Text style={[styles.planPrice, { color: colors.foreground }]}>
									{formatMoney(plan.amountMinor)}
									<Text style={[styles.planPeriod, { color: colors.mutedForeground }]}>
										{" "}/ месяц
									</Text>
								</Text>
							</View>
							<Pressable
								accessibilityLabel={
									active
										? "Текущий тариф"
										: `Оплатить ${plan.name}`
								}
								accessibilityRole="button"
								accessibilityState={{ busy, disabled: active }}
								disabled={active || Boolean(checkoutPlan)}
								onPress={() => void startCheckout(plan)}
								style={({ pressed }) => [
									styles.payButton,
									{ backgroundColor: colors.primary },
									active && styles.payButtonActive,
									pressed && styles.pressed,
								]}
							>
								{busy ? (
									<ActivityIndicator color={colors.primaryForeground} size="small" />
								) : active ? (
									<Icon name="check" size={18} color={colors.primaryForeground} />
								) : (
									<Text
										style={[
											styles.payButtonText,
											{ color: colors.primaryForeground },
										]}
									>
										Оплатить
									</Text>
								)}
							</Pressable>
						</View>
					);
				})}
				{polling ? (
					<View style={styles.pollingRow}>
						<ActivityIndicator color={colors.foreground} size="small" />
						<Text style={[styles.pollingText, { color: colors.mutedForeground }]}>
							Ждём подтверждение оплаты…
						</Text>
					</View>
				) : null}
				{message ? (
					<Text
						accessibilityRole="alert"
						style={[styles.errorText, { color: colors.destructive }]}
					>
						{message}
					</Text>
				) : null}
			</SettingsGroup>
		</>
	);
}

const styles = StyleSheet.create({
	center: {
		alignItems: "center",
		justifyContent: "center",
		minHeight: 120,
		paddingHorizontal: 18,
		paddingVertical: 18,
	},
	errorText: { fontSize: 13, lineHeight: 18, textAlign: "center" },
	emptyText: { fontSize: 13, lineHeight: 18, textAlign: "center" },
	retry: {
		alignItems: "center",
		borderRadius: 20,
		flexDirection: "row",
		gap: 7,
		marginTop: 14,
		minHeight: 40,
		paddingHorizontal: 16,
	},
	retryText: { fontSize: 14, fontWeight: "700" },
	subscriptionCard: {
		borderRadius: Radius.card,
		paddingHorizontal: 15,
		paddingVertical: 13,
	},
	subscriptionHeader: {
		alignItems: "center",
		flexDirection: "row",
		justifyContent: "space-between",
	},
	subscriptionTitle: { fontSize: 16, fontWeight: "700" },
	subscriptionMeta: { fontSize: 12, marginTop: 3 },
	statusBadge: { borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 },
	statusBadgeText: { fontSize: 12, fontWeight: "700" },
	autoRenewRow: {
		alignItems: "center",
		borderTopWidth: StyleSheet.hairlineWidth,
		flexDirection: "row",
		marginTop: 12,
		paddingTop: 12,
	},
	autoRenewCopy: { flex: 1 },
	autoRenewTitle: { fontSize: 14, fontWeight: "600" },
	autoRenewHint: { fontSize: 12, marginTop: 2 },
	planCard: {
		alignItems: "center",
		borderRadius: Radius.card,
		flexDirection: "row",
		gap: 12,
		paddingHorizontal: 15,
		paddingVertical: 13,
	},
	planCopy: { flex: 1 },
	planName: { fontSize: 16, fontWeight: "700" },
	planPrice: { fontSize: 15, fontWeight: "700", marginTop: 3 },
	planPeriod: { fontSize: 13, fontWeight: "500" },
	payButton: {
		alignItems: "center",
		borderRadius: 21,
		height: 42,
		justifyContent: "center",
		minWidth: 92,
		paddingHorizontal: 16,
	},
	payButtonActive: { opacity: 0.65 },
	payButtonText: { fontSize: 14, fontWeight: "700" },
	pressed: { opacity: 0.6 },
	pollingRow: {
		alignItems: "center",
		flexDirection: "row",
		gap: 9,
		justifyContent: "center",
		paddingVertical: 12,
	},
	pollingText: { fontSize: 13 },
});

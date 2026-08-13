import Constants from "expo-constants";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import {
	ActivityIndicator,
	KeyboardAvoidingView,
	Platform,
	ScrollView,
	StyleSheet,
	Text,
	View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { AuthScreen } from "@/components/auth/auth-screen";
import { NativeScreenHeader } from "@/components/shell/native-screen-header";
import { CircleButton } from "@/components/shell/circle-button";
import { IdentitySummary } from "@/components/settings/identity-summary";
import { ProfileNameEditor } from "@/components/settings/profile-name-editor";
import { SettingsGroup } from "@/components/settings/settings-group";
import { SettingsRow } from "@/components/settings/settings-row";
import { WebBillingSettings } from "@/components/settings/web-billing-settings";
import { NativeBillingSettings } from "@/components/settings/native-billing-settings";
import { Icon } from "@/components/ui/icon";
import { Layout } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import type { ThemePreference } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";
import { confirmAsync } from "@/lib/dialogs";
import { useMobileSession } from "@/src/auth/mobile-session";
import {
	MOBILE_DEV_MODE_CYCLE,
	MOBILE_DEV_MODE_LABELS,
	useMobileDeveloperMode,
} from "@/src/product-chat/runtime-provider";
import { constructionEstimateAccess } from "@/src/verticals/construction-estimates/access";

function AccountSkeleton() {
	const { colors } = useTheme();
	return (
		<SafeAreaView
			accessibilityLabel="Загрузка личного кабинета"
			edges={["top", "bottom"]}
			style={[styles.safe, { backgroundColor: colors.settingsBackground }]}
		>
			<NativeScreenHeader onBack={() => undefined} title="Настроить КолИ" />
			<View style={styles.skeletonContent}>
				<View style={styles.skeletonHero}>
					<View style={[styles.skeletonAvatar, { backgroundColor: colors.muted }]} />
					<View style={styles.skeletonCopy}>
						<View style={[styles.skeletonName, { backgroundColor: colors.muted }]} />
						<View style={[styles.skeletonEmail, { backgroundColor: colors.muted }]} />
					</View>
				</View>
				{[0, 1, 2].map((index) => (
					<View
						key={index}
						style={[
							styles.skeletonGroup,
							{ backgroundColor: colors.surfaceRaised },
						]}
					/>
				))}
				<ActivityIndicator color={colors.foreground} style={styles.skeletonSpinner} />
			</View>
		</SafeAreaView>
	);
}

function AccessDetails({
	capabilityCount,
	entitlementCount,
	role,
}: {
	capabilityCount: number;
	entitlementCount: number;
	role: string;
}) {
	const { colors } = useTheme();
	const rows = [
		["Роль", role],
		["Права", `${capabilityCount} активных`],
		["Продукты", entitlementCount ? `${entitlementCount} доступно` : "Нет подключённых"],
	] as const;
	return (
		<View
			accessibilityLabel="Сведения о доступе"
			style={[styles.accessDetails, { borderTopColor: colors.border }]}
		>
			{rows.map(([label, value]) => (
				<View key={label} style={styles.accessDetailRow}>
					<Text style={[styles.accessLabel, { color: colors.mutedForeground }]}>
						{label}
					</Text>
					<Text style={[styles.accessValue, { color: colors.foreground }]}>
						{value}
					</Text>
				</View>
			))}
		</View>
	);
}

function ThemeChoices({
	onSelect,
	selected,
}: {
	onSelect: (preference: ThemePreference) => void;
	selected: ThemePreference;
}) {
	const { colors } = useTheme();
	const options: readonly { label: string; value: ThemePreference }[] = [
		{ label: "Как на устройстве", value: "system" },
		{ label: "Светлая", value: "light" },
		{ label: "Тёмная", value: "dark" },
	];
	return (
		<View
			accessibilityLabel="Выбор оформления"
			style={[styles.themeChoices, { borderTopColor: colors.border }]}
		>
			{options.map((option, index) => (
				<SettingsRow
					icon="appearance"
					key={option.value}
					last={index === options.length - 1}
					onPress={() => onSelect(option.value)}
					title={option.label}
					trailing={
						option.value === selected ? (
							<Icon name="check" size={18} color={colors.foreground} />
						) : (
							<View style={styles.choicePlaceholder} />
						)
					}
				/>
			))}
		</View>
	);
}

export default function AccountScreen() {
	const router = useRouter();
	const { paymentIntent } = useLocalSearchParams<{
		paymentIntent?: string | string[];
	}>();
	const session = useMobileSession();
	const { colors, isDark, preference, setPreference } = useTheme();
	const { mode: devMode, setMode: setDevMode } = useMobileDeveloperMode();
	const [nameDraft, setNameDraft] = useState<string | null>(null);
	const [saving, setSaving] = useState(false);
	const [loggingOut, setLoggingOut] = useState(false);
	const [accessExpanded, setAccessExpanded] = useState(false);
	const [appearanceExpanded, setAppearanceExpanded] = useState(false);
	const [error, setError] = useState<string | null>(null);

	if (session.status === "restoring") return <AccountSkeleton />;
	if (session.status === "signed-out" || !session.user) return <AuthScreen />;

	const user = session.user;
	const displayName = nameDraft ?? user.name;
	const normalizedName = displayName.trim();
	const dirty = normalizedName !== user.name;
	const canSave =
		!saving && normalizedName.length >= 1 && normalizedName.length <= 160 && dirty;
	const estimateAccess = constructionEstimateAccess(user);
	const roleLabel = user.role === "owner" ? "Владелец" : "Пользователь";
	const appearanceLabel =
		preference === "system"
			? isDark
				? "Системное · тёмное"
				: "Системное · светлое"
			: preference === "dark"
				? "Тёмное"
				: "Светлое";
	const returnedPaymentIntent =
		typeof paymentIntent === "string" ? paymentIntent : undefined;

	const goBack = () => {
		if (router.canGoBack()) router.back();
		else router.replace("/app?client=mobile");
	};
	const requestBack = () => {
		if (!dirty) {
			goBack();
			return;
		}
		void confirmAsync(
			"Не сохранены изменения",
			"Выйти без сохранения имени?",
			{ acceptLabel: "Не сохранять", cancelLabel: "Остаться", destructive: true },
		).then((confirmed) => {
			if (confirmed) goBack();
		});
	};
	const save = async () => {
		if (!canSave) return;
		setSaving(true);
		setError(null);
		try {
			await session.updateProfile({ name: normalizedName });
			setNameDraft(null);
			haptics.success();
		} catch (reason) {
			setError(
				reason instanceof Error
					? reason.message
					: "Не удалось сохранить профиль.",
			);
			haptics.error();
		} finally {
			setSaving(false);
		}
	};
	const requestLogout = () => {
		void confirmAsync(
			"Выйти из аккаунта?",
			"Для следующего входа понадобятся почта и пароль.",
			{ acceptLabel: "Выйти", destructive: true },
		).then((confirmed) => {
			if (!confirmed) return;
			setLoggingOut(true);
			haptics.selection();
			void session.logout();
		});
	};

	return (
		<SafeAreaView
			edges={["top", "bottom"]}
			style={[styles.safe, { backgroundColor: colors.settingsBackground }]}
		>
			<NativeScreenHeader
				onBack={requestBack}
				title="Настроить КолИ"
				trailing={
					<CircleButton
						accessibilityLabel="Закрыть настройки"
						accessibilityRole="button"
						onPress={() => {
							haptics.selection();
							requestBack();
						}}
					>
						<Icon name="close" size={22} color={colors.foreground} />
					</CircleButton>
				}
			/>
			<KeyboardAvoidingView
				behavior={Platform.OS === "ios" ? "padding" : undefined}
				style={styles.flex}
			>
				<ScrollView
					contentContainerStyle={styles.content}
					contentInsetAdjustmentBehavior="automatic"
					keyboardDismissMode="interactive"
					keyboardShouldPersistTaps="handled"
					showsVerticalScrollIndicator={false}
				>
					<IdentitySummary
						email={user.email}
						isOwner={user.isPlatformOwner}
						name={user.name}
					/>

					<SettingsGroup title="Аккаунт">
						<ProfileNameEditor
							canSave={canSave}
							error={error}
							onChangeText={(value) => {
								setNameDraft(value);
								if (error) setError(null);
							}}
							onSave={() => void save()}
							saving={saving}
							value={displayName}
						/>
					</SettingsGroup>

					<SettingsGroup title="Персонализация">
						<SettingsRow
							icon="agent"
							title="Агент"
							value={user.preferredAgentProfile}
						/>
						<SettingsRow
							icon="model"
							title="Модель"
							value={user.preferredModel ?? "Автоматически"}
						/>
						<SettingsRow
							icon="shield"
							onPress={() => {
								const next =
									MOBILE_DEV_MODE_CYCLE[
										(MOBILE_DEV_MODE_CYCLE.indexOf(devMode) + 1) %
											MOBILE_DEV_MODE_CYCLE.length
									] ?? "full";
								haptics.selection();
								setDevMode(next);
							}}
							title="Режим разработчика"
							value={MOBILE_DEV_MODE_LABELS[devMode]}
						/>
						<SettingsRow
							icon="appearance"
							last={!appearanceExpanded}
							onPress={() => setAppearanceExpanded((value) => !value)}
							title="Оформление"
							trailing={
								<Icon
									name={appearanceExpanded ? "chevron-up" : "chevron-down"}
									size={18}
									color={colors.mutedForeground}
								/>
							}
							value={appearanceLabel}
						/>
						{appearanceExpanded ? (
							<ThemeChoices
								onSelect={(next) => {
									setPreference(next);
									setAppearanceExpanded(false);
								}}
								selected={preference}
							/>
						) : null}
					</SettingsGroup>

					<SettingsGroup title="Приложение">
						<SettingsRow
							accessibilityHint={estimateAccess.enabled ? "Открыть сметы" : estimateAccess.reason}
							disabled={!estimateAccess.enabled}
							icon="document"
							last
							onPress={
								estimateAccess.enabled
									? () => router.push("/estimates?client=mobile")
									: undefined
							}
							title="Сметы"
							value={estimateAccess.enabled ? "Открыть" : "Нет доступа"}
						/>
					</SettingsGroup>

					{Platform.OS === "web" ? (
						<WebBillingSettings
							authorizedFetch={session.authorizedFetch}
							refreshProfile={session.refreshProfile}
							returnedIntent={returnedPaymentIntent}
						/>
					) : (
						<NativeBillingSettings />
					)}

					<SettingsGroup title="Безопасность и доступ">
						<SettingsRow
							icon="shield"
							last
							onPress={() => setAccessExpanded((value) => !value)}
							title="Роль и доступ"
							trailing={
								<Icon
									name={accessExpanded ? "chevron-up" : "chevron-down"}
									size={18}
									color={colors.mutedForeground}
								/>
							}
							value={roleLabel}
						/>
						{accessExpanded ? (
							<AccessDetails
								capabilityCount={user.capabilities.length}
								entitlementCount={user.entitlements.length}
								role={roleLabel}
							/>
						) : null}
					</SettingsGroup>

					<SettingsGroup>
						<SettingsRow
							destructive
							disabled={loggingOut}
							icon="logout"
							last
							onPress={requestLogout}
							title={loggingOut ? "Выходим…" : "Выйти из аккаунта"}
							trailing={loggingOut ? <ActivityIndicator color={colors.destructive} /> : undefined}
						/>
					</SettingsGroup>

					<Text style={[styles.version, { color: colors.mutedForeground }]}>
						Kolibri V3 · {Constants.expoConfig?.version ?? "1.0.0"}
					</Text>
				</ScrollView>
			</KeyboardAvoidingView>
		</SafeAreaView>
	);
}

const styles = StyleSheet.create({
	safe: { flex: 1 },
	flex: { flex: 1 },
	content: {
		gap: 20,
		paddingBottom: 28,
		paddingHorizontal: Layout.edgeInset,
	},
	accessDetails: {
		borderTopWidth: StyleSheet.hairlineWidth,
		gap: 10,
		marginLeft: 56,
		paddingBottom: 14,
		paddingRight: 14,
		paddingTop: 12,
	},
	accessDetailRow: { alignItems: "center", flexDirection: "row", gap: 12 },
	accessLabel: { flex: 1, fontSize: 13, lineHeight: 18 },
	accessValue: { fontSize: 13, fontWeight: "600", lineHeight: 18 },
	version: { fontSize: 12, lineHeight: 17, textAlign: "center" },
	themeChoices: { borderTopWidth: StyleSheet.hairlineWidth },
	choicePlaceholder: { height: 18, width: 18 },
	skeletonContent: { gap: 20, paddingHorizontal: Layout.edgeInset },
	skeletonHero: { alignItems: "center", flexDirection: "row", minHeight: 92, paddingHorizontal: 4 },
	skeletonAvatar: { borderRadius: 32, height: 64, width: 64 },
	skeletonCopy: { flex: 1, gap: 9, marginLeft: 15 },
	skeletonName: { borderRadius: 6, height: 20, width: "46%" },
	skeletonEmail: { borderRadius: 5, height: 14, width: "72%" },
	skeletonGroup: { borderRadius: 18, height: 112 },
	skeletonSpinner: { position: "absolute", right: Layout.edgeInset + 4, top: 4 },
});

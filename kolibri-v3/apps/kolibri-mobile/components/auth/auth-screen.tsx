import { useEffect, useRef, useState } from "react";
import {
	ActivityIndicator,
	KeyboardAvoidingView,
	Platform,
	Pressable,
	StyleSheet,
	Text,
	TextInput,
	View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Link } from "expo-router";

import {
	FontSize,
	Layout,
	LetterSpacing,
	LineHeight,
	Radius,
	Spacing,
	typography,
} from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { useMobileSession } from "@/src/auth/mobile-session";

export function AuthScreen() {
	const { colors } = useTheme();
	const session = useMobileSession();
	const [mode, setMode] = useState<"login" | "register" | "magic-link">(
		"login",
	);
	const [email, setEmail] = useState("");
	const [name, setName] = useState("");
	const [password, setPassword] = useState("");
	const [submitting, setSubmitting] = useState(false);
	const [magicState, setMagicState] = useState<
		"idle" | "sending" | "sent" | "error"
	>("idle");
	const [magicLink, setMagicLink] = useState<string | null>(null);
	const [magicError, setMagicError] = useState<string | null>(null);
	const emailInputRef = useRef<TextInput | null>(null);
	const passwordInputRef = useRef<TextInput | null>(null);

	useEffect(() => {
		if (Platform.OS !== "web" || mode !== "login") return;

		const readAutofilledValue = (input: TextInput | null) => {
			const candidate = (input as unknown as { value?: unknown } | null)?.value;
			return typeof candidate === "string" ? candidate : "";
		};
		const synchronizeAutofill = () => {
			const autofilledEmail = readAutofilledValue(emailInputRef.current);
			const autofilledPassword = readAutofilledValue(passwordInputRef.current);
			if (autofilledEmail) setEmail((current) => current || autofilledEmail);
			if (autofilledPassword) {
				setPassword((current) => current || autofilledPassword);
			}
		};

		synchronizeAutofill();
		const timers = [120, 450, 1_000].map((delay) =>
			setTimeout(synchronizeAutofill, delay),
		);
		return () => timers.forEach(clearTimeout);
	}, [mode]);

	const passwordMinLength = mode === "register" ? 12 : 1;
	const canSubmit =
		email.trim().length > 0 &&
		password.length >= passwordMinLength &&
		(mode === "login" || name.trim().length > 0);

	const submit = async () => {
		if (!canSubmit || submitting) return;
		setSubmitting(true);
		try {
			if (mode === "login") {
				await session.login({ email: email.trim(), password });
			} else {
				await session.register({
					email: email.trim(),
					name: name.trim(),
					password,
				});
			}
		} finally {
			setSubmitting(false);
		}
	};

	const sendMagicLink = async () => {
		const normalizedEmail = email.trim();
		if (!normalizedEmail || submitting) return;
		setSubmitting(true);
		setMagicError(null);
		try {
			const result = await session.requestMagicLink(normalizedEmail);
			setMagicLink(result.magicLink ?? null);
			setMagicState("sent");
		} catch (reason) {
			setMagicError(
				reason instanceof Error ? reason.message : "Не удалось отправить ссылку.",
			);
			setMagicState("error");
		} finally {
			setSubmitting(false);
		}
	};

	return (
		<SafeAreaView
			edges={["top", "bottom"]}
			style={[styles.safe, { backgroundColor: colors.background }]}
		>
			<KeyboardAvoidingView
				behavior={Platform.OS === "ios" ? "padding" : undefined}
				style={styles.keyboard}
			>
				<View style={styles.content}>
					<View style={styles.brand}>
						<View style={[styles.mark, { backgroundColor: colors.foreground }]}>
							<Text
								style={[styles.markText, { color: colors.primaryForeground }]}
							>
								K
							</Text>
						</View>
						<Text style={[styles.title, { color: colors.foreground }]}>
							Kolibri AI
						</Text>
						<Text style={[styles.subtitle, { color: colors.mutedForeground }]}>
							Проекты, документы и агентная работа
						</Text>
					</View>

					<View style={styles.form}>
						{mode === "magic-link" ? (
							<>
								<TextInput
									accessibilityLabel="Электронная почта"
									autoCapitalize="none"
									autoComplete="email"
									keyboardType="email-address"
									onChangeText={setEmail}
									placeholder="Электронная почта"
									placeholderTextColor={colors.mutedForeground}
									style={[
										styles.input,
										{
											backgroundColor: colors.surface,
											borderColor: colors.border,
											color: colors.foreground,
										},
									]}
									value={email}
								/>
								<Pressable
									accessibilityRole="button"
									accessibilityState={{ disabled: submitting }}
									disabled={submitting}
									onPress={sendMagicLink}
									style={({ pressed }) => [
										styles.primary,
										{ backgroundColor: colors.foreground },
										pressed && styles.pressed,
									]}
								>
									{submitting ? (
										<ActivityIndicator color={colors.primaryForeground} />
									) : (
										<Text
											style={[
												styles.primaryText,
												{ color: colors.primaryForeground },
											]}
										>
											Отправить ссылку
										</Text>
									)}
								</Pressable>
								{magicState === "sent" ? (
									<Text style={[styles.hint, { color: colors.success }]}>
										Ссылка отправлена. Проверьте почту.
									</Text>
								) : null}
								{magicLink ? (
									<Link
										href={`/auth/magic-link?email=${encodeURIComponent(email.trim())}&token=${encodeURIComponent(magicLink)}`}
										style={[styles.secondaryText, { color: colors.foreground }]}
									>
										Открыть ссылку входа
									</Link>
								) : null}
								{magicError ? (
									<Text style={[styles.error, { color: colors.destructive }]}>
										{magicError}
									</Text>
								) : null}
								<Pressable
									accessibilityRole="button"
									onPress={() => setMode("login")}
									style={({ pressed }) => [
										styles.secondary,
										pressed && styles.pressed,
									]}
								>
									<Text style={[styles.secondaryText, { color: colors.foreground }]}>
										Войти с паролем
									</Text>
								</Pressable>
							</>
						) : (
							<>
						{mode === "register" ? (
							<TextInput
								accessibilityLabel="Имя"
								autoCapitalize="words"
								autoComplete="name"
								onChangeText={setName}
								placeholder="Имя"
								placeholderTextColor={colors.mutedForeground}
								style={[
									styles.input,
									{
										backgroundColor: colors.surface,
										borderColor: colors.border,
										color: colors.foreground,
									},
								]}
								value={name}
							/>
						) : null}
						<TextInput
							accessibilityLabel="Электронная почта"
							autoCapitalize="none"
							autoComplete="email"
							importantForAutofill="yes"
							keyboardType="email-address"
							onChangeText={setEmail}
							placeholder="Электронная почта"
							placeholderTextColor={colors.mutedForeground}
							style={[
								styles.input,
								{
									backgroundColor: colors.surface,
									borderColor: colors.border,
									color: colors.foreground,
								},
							]}
							ref={emailInputRef}
							textContentType="username"
							value={email}
						/>
						<TextInput
							accessibilityLabel="Пароль"
							autoCapitalize="none"
							autoComplete={
								mode === "login" ? "current-password" : "new-password"
							}
							importantForAutofill="yes"
							onChangeText={setPassword}
							onSubmitEditing={submit}
							placeholder="Пароль"
							placeholderTextColor={colors.mutedForeground}
							secureTextEntry
							style={[
								styles.input,
								{
									backgroundColor: colors.surface,
									borderColor: colors.border,
									color: colors.foreground,
								},
							]}
							ref={passwordInputRef}
							textContentType={mode === "login" ? "password" : "newPassword"}
							value={password}
						/>
						{mode === "register" && password.length > 0 && password.length < 12 ? (
							<Text
								style={[styles.hint, { color: colors.mutedForeground }]}
							>
								Для регистрации нужен пароль не короче 12 символов.
							</Text>
						) : null}

						{session.error ? (
							<Text
								accessibilityLiveRegion="polite"
								style={[styles.error, { color: colors.destructive }]}
							>
								{session.error}
							</Text>
						) : null}

						<Pressable
							accessibilityRole="button"
							accessibilityState={{ disabled: !canSubmit || submitting }}
							disabled={!canSubmit || submitting}
							onPress={submit}
							style={({ pressed }) => [
								styles.primary,
								{ backgroundColor: colors.foreground },
								(!canSubmit || submitting) && styles.disabled,
								pressed && styles.pressed,
							]}
						>
							{submitting ? (
								<ActivityIndicator color={colors.primaryForeground} />
							) : (
								<Text
									style={[
										styles.primaryText,
										{ color: colors.primaryForeground },
									]}
								>
									{mode === "login" ? "Войти" : "Создать аккаунт"}
								</Text>
							)}
						</Pressable>

						<Pressable
							accessibilityRole="button"
							onPress={() =>
								setMode((current) =>
									current === "login" ? "register" : "login",
								)
							}
							style={({ pressed }) => [
								styles.secondary,
								pressed && styles.pressed,
							]}
						>
							<Text
								style={[styles.secondaryText, { color: colors.foreground }]}
							>
								{mode === "login"
									? "Создать аккаунт"
									: "У меня уже есть аккаунт"}
							</Text>
						</Pressable>
								<Pressable
									accessibilityRole="button"
									onPress={() => {
										setMagicState("idle");
										setMagicLink(null);
										setMagicError(null);
										setMode("magic-link");
									}}
									style={({ pressed }) => [
										styles.secondary,
										pressed && styles.pressed,
									]}
								>
									<Text
										style={[styles.secondaryText, { color: colors.foreground }]}
									>
										Войти по ссылке
									</Text>
								</Pressable>
							</>
						)}
					</View>
				</View>
			</KeyboardAvoidingView>
		</SafeAreaView>
	);
}

const styles = StyleSheet.create({
	safe: { flex: 1 },
	keyboard: { flex: 1 },
	content: {
		flex: 1,
		justifyContent: "center",
		paddingHorizontal: Layout.edgeInset + Spacing.sm,
		paddingBottom: Spacing.xxl,
	},
	brand: { alignItems: "center", marginBottom: Spacing.xxxl + Spacing.sm },
	mark: {
		alignItems: "center",
		borderRadius: Radius.control,
		height: 64,
		justifyContent: "center",
		marginBottom: Layout.composerInset,
		width: 64,
	},
	markText: typography.amountXL,
	title: { ...typography.hScreen, letterSpacing: LetterSpacing.tighter },
	subtitle: {
		...typography.body,
		marginTop: Spacing.sm,
		textAlign: "center",
	},
	form: { gap: Spacing.lg },
	input: {
		borderRadius: Radius.input,
		borderWidth: StyleSheet.hairlineWidth,
		...typography.body,
		minHeight: 56,
		paddingHorizontal: Spacing.lg,
	},
	hint: {
		fontSize: FontSize.footnote,
		lineHeight: LineHeight.compact,
		paddingHorizontal: Spacing.xs,
	},
	error: {
		fontSize: FontSize.small,
		lineHeight: LineHeight.small,
		paddingHorizontal: Spacing.xs,
	},
	primary: {
		alignItems: "center",
		borderRadius: Radius.circle,
		height: 56,
		justifyContent: "center",
		marginTop: Spacing.xs,
	},
	primaryText: { ...typography.pillLabel },
	secondary: { alignItems: "center", padding: Spacing.md },
	secondaryText: { ...typography.settingsRow },
	disabled: { opacity: 0.36 },
	pressed: { opacity: 0.68 },
});

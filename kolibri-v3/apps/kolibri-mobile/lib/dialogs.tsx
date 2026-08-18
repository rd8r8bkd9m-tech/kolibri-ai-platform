import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
	Alert,
	Modal,
	Platform,
	Pressable,
	StyleSheet,
	Text,
	TextInput,
	View,
} from "react-native";

import { useTheme } from "@/hooks/use-theme";

type ActionSheetOption = {
	text: string;
	style?: "default" | "cancel" | "destructive";
	onPress?: () => void;
};

type PendingSheet = {
	title: string;
	options: readonly ActionSheetOption[];
	resolve: (index: number) => void;
};

type PendingPrompt = {
	title: string;
	message: string | undefined;
	initialValue: string;
	acceptLabel: string;
	cancelLabel: string;
	resolve: (value: string | null) => void;
};

let pendingSheet: PendingSheet | null = null;
let pendingPrompt: PendingPrompt | null = null;
let sheetListeners = new Set<() => void>();
let promptListeners = new Set<() => void>();

function notifySheet() {
	for (const listener of sheetListeners) listener();
}

function notifyPrompt() {
	for (const listener of promptListeners) listener();
}

/**
 * Ask for a single-line text value on every platform. Returns the accepted
 * string, or null when the user cancels.
 */
export function promptAsync(
	title: string,
	options: {
		message?: string;
		initialValue?: string;
		acceptLabel?: string;
		cancelLabel?: string;
	} = {},
): Promise<string | null> {
	return new Promise((resolve) => {
		pendingPrompt = {
			title,
			message: options.message,
			initialValue: options.initialValue ?? "",
			acceptLabel: options.acceptLabel ?? "Сохранить",
			cancelLabel: options.cancelLabel ?? "Отмена",
			resolve: (value) => {
				pendingPrompt = null;
				notifyPrompt();
				resolve(value);
			},
		};
		notifyPrompt();
	});
}

/**
 * Show a native-style action sheet on every platform. React Native Web leaves
 * `Alert.alert` as a no-op, so the PWA silently dropped the thread actions;
 * this module bridges that gap with a lightweight modal host.
 */
export function actionSheetAsync(
	title: string,
	options: readonly ActionSheetOption[],
): Promise<number> {
	if (Platform.OS === "web") {
		return new Promise((resolve) => {
			pendingSheet = {
				title,
				options,
				resolve: (index) => {
					pendingSheet = null;
					notifySheet();
					resolve(index);
				},
			};
			notifySheet();
		});
	}
	return new Promise((resolve) => {
		Alert.alert(
			title,
			undefined,
			options.map((option, index) => ({
				text: option.text,
				style: option.style,
				onPress: () => {
					option.onPress?.();
					resolve(index);
				},
			})),
			{ cancelable: true, onDismiss: () => resolve(-1) },
		);
	});
}

export function confirmAsync(
	title: string,
	message: string | undefined,
	options: {
		acceptLabel: string;
		cancelLabel?: string;
		destructive?: boolean;
	} = { acceptLabel: "OK" },
): Promise<boolean> {
	if (Platform.OS === "web" && typeof window !== "undefined") {
		const text = message ? `${title}\n\n${message}` : title;
		return Promise.resolve(window.confirm(text));
	}
	return new Promise((resolve) => {
		Alert.alert(title, message, [
			{
				text: options.cancelLabel ?? "Отмена",
				style: "cancel",
				onPress: () => resolve(false),
			},
			{
				text: options.acceptLabel,
				style: options.destructive ? "destructive" : "default",
				onPress: () => resolve(true),
			},
		]);
	});
}

/**
 * Mount once in the app root. Renders the web action sheet as a modal;
 * on native platforms it renders nothing (Alert handles it).
 */
export function DialogsHost() {
	const { colors } = useTheme();
	const [sheet, setSheet] = useState<PendingSheet | null>(null);
	const [prompt, setPrompt] = useState<PendingPrompt | null>(null);
	const [promptValue, setPromptValue] = useState("");

	useEffect(() => {
		const listener = () => setSheet(pendingSheet);
		sheetListeners.add(listener);
		return () => {
			sheetListeners.delete(listener);
		};
	}, []);

	useEffect(() => {
		const listener = () => {
			setPrompt(pendingPrompt);
			setPromptValue(pendingPrompt?.initialValue ?? "");
		};
		promptListeners.add(listener);
		return () => {
			promptListeners.delete(listener);
		};
	}, []);

	const close = useCallback((index: number) => {
		sheet?.resolve(index);
	}, [sheet]);

	const submitPrompt = useCallback(() => {
		const value = promptValue.trim();
		if (!value || !prompt) return;
		prompt.resolve(value);
		setPrompt(null);
	}, [prompt, promptValue]);

	const cancelPrompt = useCallback(() => {
		prompt?.resolve(null);
		setPrompt(null);
	}, [prompt]);

	return (
		<>
			{Platform.OS === "web" && sheet ? (
				<Modal
					animationType="fade"
					onRequestClose={() => close(-1)}
					transparent
					visible
				>
					<View style={[styles.backdrop, { backgroundColor: colors.overlay }]}>
						<Pressable
							accessibilityLabel="Закрыть меню действий"
							onPress={() => close(-1)}
							style={StyleSheet.absoluteFill}
						/>
						<View
							accessibilityViewIsModal
							style={[styles.sheet, { backgroundColor: colors.surfaceRaised }]}
						>
							<Text style={[styles.title, { color: colors.foreground }]}>
								{sheet.title}
							</Text>
							{sheet.options.map((option, index) => (
								<Pressable
									key={`${option.text}-${index}`}
									accessibilityRole="button"
									onPress={() => {
										option.onPress?.();
										close(index);
									}}
									style={({ pressed }) => [
										styles.option,
										{ borderTopColor: colors.border },
										option.style === "destructive" && {
											backgroundColor: colors.destructiveSurface,
										},
										option.style === "cancel" && {
											backgroundColor: colors.muted,
										},
										pressed && styles.pressed,
									]}
								>
									<Text
										style={[
											styles.optionText,
											{
												color:
													option.style === "destructive"
														? colors.destructive
														: colors.foreground,
											},
										]}
									>
										{option.text}
									</Text>
								</Pressable>
							))}
						</View>
					</View>
				</Modal>
			) : null}
			{prompt ? (
				<Modal
					animationType="slide"
					onRequestClose={cancelPrompt}
					transparent
					visible
				>
					<View
						style={[
							styles.backdrop,
							styles.sheetBackdrop,
							{ backgroundColor: colors.overlay },
						]}
					>
						<Pressable
							accessibilityLabel="Закрыть окно ввода"
							onPress={cancelPrompt}
							style={StyleSheet.absoluteFill}
						/>
						<View
							accessibilityViewIsModal
							style={[
								styles.sheet,
								styles.promptSheet,
								styles.bottomSheet,
								{ backgroundColor: colors.surfaceRaised },
							]}
						>
							<Text style={[styles.title, { color: colors.foreground }]}>
								{prompt.title}
							</Text>
							{prompt.message ? (
								<Text
									style={[
										styles.promptMessage,
										{ color: colors.mutedForeground },
									]}
								>
									{prompt.message}
								</Text>
							) : null}
							<TextInput
								autoFocus
								accessibilityLabel={prompt.title}
								maxLength={240}
								onChangeText={setPromptValue}
								onSubmitEditing={submitPrompt}
								placeholder={prompt.initialValue}
								placeholderTextColor={colors.mutedForeground}
								returnKeyType="done"
								selectionColor={colors.send}
								style={[
									styles.promptInput,
									{
										backgroundColor: colors.muted,
										color: colors.foreground,
									},
								]}
								value={promptValue}
							/>
							<View style={styles.promptActions}>
								<Pressable
									accessibilityRole="button"
									onPress={cancelPrompt}
									style={({ pressed }) => [
										styles.promptButton,
										pressed && styles.pressed,
									]}
								>
									<Text
										style={[
											styles.promptCancelText,
											{ color: colors.mutedForeground },
										]}
									>
										{prompt.cancelLabel}
									</Text>
								</Pressable>
								<Pressable
									accessibilityRole="button"
									accessibilityState={{ disabled: !promptValue.trim() }}
									disabled={!promptValue.trim()}
									onPress={submitPrompt}
									style={({ pressed }) => [
										styles.promptButton,
										!promptValue.trim() && styles.promptDisabled,
										pressed && styles.pressed,
									]}
								>
									<Text
										style={[
											styles.promptAcceptText,
											{ color: colors.send },
										]}
									>
										{prompt.acceptLabel}
									</Text>
								</Pressable>
							</View>
						</View>
					</View>
				</Modal>
			) : null}
		</>
	);
}

const styles = StyleSheet.create({
	backdrop: {
		alignItems: "center",
		flex: 1,
		justifyContent: "flex-end",
		padding: 12,
	},
	sheetBackdrop: { justifyContent: "flex-end" },
	bottomSheet: {
		borderBottomLeftRadius: 0,
		borderBottomRightRadius: 0,
		marginBottom: -12,
		paddingBottom: 20,
	},
	sheet: {
		borderTopLeftRadius: 20,
		borderTopRightRadius: 20,
		borderBottomLeftRadius: 16,
		borderBottomRightRadius: 16,
		maxWidth: 520,
		overflow: "hidden",
		width: "100%",
	},
	promptSheet: { paddingBottom: 10, paddingHorizontal: 16 },
	title: {
		fontSize: 15,
		fontWeight: "600",
		paddingHorizontal: 16,
		paddingVertical: 14,
		textAlign: "center",
	},
	promptMessage: {
		fontSize: 13,
		lineHeight: 18,
		paddingHorizontal: 4,
		paddingBottom: 12,
		textAlign: "center",
	},
	promptInput: {
		borderRadius: 11,
		fontSize: 16,
		minHeight: 46,
		paddingHorizontal: 13,
		paddingVertical: 9,
	},
	promptActions: {
		flexDirection: "row",
		gap: 8,
		justifyContent: "flex-end",
		paddingTop: 12,
	},
	promptButton: {
		alignItems: "center",
		borderRadius: 14,
		justifyContent: "center",
		minHeight: 40,
		minWidth: 84,
		paddingHorizontal: 12,
	},
	promptDisabled: { opacity: 0.45 },
	promptCancelText: { fontSize: 15, fontWeight: "600" },
	promptAcceptText: { fontSize: 15, fontWeight: "700" },
	option: {
		alignItems: "center",
		borderTopWidth: StyleSheet.hairlineWidth,
		minHeight: 52,
		justifyContent: "center",
		paddingHorizontal: 16,
	},
	pressed: { opacity: 0.55 },
	optionText: { fontSize: 17, fontWeight: "500" },
});

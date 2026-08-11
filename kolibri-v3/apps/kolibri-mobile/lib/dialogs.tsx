import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
	Alert,
	Modal,
	Platform,
	Pressable,
	StyleSheet,
	Text,
	View,
} from "react-native";

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

let pendingSheet: PendingSheet | null = null;
let sheetListeners = new Set<() => void>();

function notifySheet() {
	for (const listener of sheetListeners) listener();
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
	const [sheet, setSheet] = useState<PendingSheet | null>(null);

	useEffect(() => {
		const listener = () => setSheet(pendingSheet);
		sheetListeners.add(listener);
		return () => {
			sheetListeners.delete(listener);
		};
	}, []);

	const close = useCallback((index: number) => {
		sheet?.resolve(index);
	}, [sheet]);

	if (Platform.OS !== "web" || !sheet) return null;

	return (
		<Modal
			animationType="fade"
			onRequestClose={() => close(-1)}
			transparent
			visible
		>
			<View style={styles.backdrop}>
				<Pressable
					accessibilityLabel="Закрыть меню действий"
					onPress={() => close(-1)}
					style={StyleSheet.absoluteFill}
				/>
				<View accessibilityViewIsModal style={styles.sheet}>
					<Text style={styles.title}>{sheet.title}</Text>
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
								option.style === "destructive" && styles.destructive,
								option.style === "cancel" && styles.cancel,
								pressed && styles.pressed,
							]}
						>
							<Text
								style={[
									styles.optionText,
									option.style === "destructive" && styles.destructiveText,
									option.style === "cancel" && styles.cancelText,
								]}
							>
								{option.text}
							</Text>
						</Pressable>
					))}
				</View>
			</View>
		</Modal>
	);
}

const styles = StyleSheet.create({
	backdrop: {
		alignItems: "center",
		backgroundColor: "rgba(0, 0, 0, 0.45)",
		flex: 1,
		justifyContent: "flex-end",
		padding: 12,
	},
	sheet: {
		backgroundColor: "#1c1c1e",
		borderRadius: 16,
		maxWidth: 520,
		overflow: "hidden",
		width: "100%",
	},
	title: {
		color: "#ebebf0",
		fontSize: 15,
		fontWeight: "600",
		paddingHorizontal: 16,
		paddingVertical: 14,
		textAlign: "center",
	},
	option: {
		alignItems: "center",
		borderTopColor: "rgba(235, 235, 240, 0.14)",
		borderTopWidth: StyleSheet.hairlineWidth,
		minHeight: 52,
		justifyContent: "center",
		paddingHorizontal: 16,
	},
	destructive: { backgroundColor: "rgba(255, 69, 58, 0.08)" },
	cancel: { backgroundColor: "rgba(255, 255, 255, 0.06)" },
	pressed: { opacity: 0.55 },
	optionText: { color: "#ebebf0", fontSize: 17, fontWeight: "500" },
	destructiveText: { color: "#ff453a" },
	cancelText: { color: "#ebebf0", fontWeight: "600" },
});

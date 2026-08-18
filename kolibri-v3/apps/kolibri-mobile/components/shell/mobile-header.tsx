import { useAui, useAuiState } from "@assistant-ui/react-native";
import { useNavigation } from "expo-router";
import type { DrawerNavigationProp } from "expo-router/build/react-navigation/drawer/types";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { CircleButton } from "@/components/shell/circle-button";
import { HamburgerMark } from "@/components/shell/hamburger-mark";
import { Icon } from "@/src/components/icons/Icon";
import {
	FontSize,
	FontWeight,
	Layout,
	LetterSpacing,
	Radius,
	Spacing,
} from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";
import { actionSheetAsync, promptAsync } from "@/lib/dialogs";
import { releaseWebFocus } from "@/src/accessibility/release-web-focus";

export function MobileHeader() {
	const navigation =
		useNavigation<DrawerNavigationProp<{ index: undefined }, "index">>();
	const aui = useAui();
	const { colors } = useTheme();
	const isEmpty = useAuiState((state) => state.thread.isEmpty);
	const isRunning = useAuiState((state) => state.thread.isRunning);
	const mainThreadId = useAuiState((state) => state.threads.mainThreadId);
	const threadTitle = useAuiState((state) => {
		const item = state.threads.threadItems.find(
			(entry) => entry.id === state.threads.mainThreadId,
		);
		return item?.title;
	});

	const openDrawer = () => {
		haptics.selection();
		releaseWebFocus();
		navigation.openDrawer();
	};

	const overflow = () => {
		if (!mainThreadId) return;
		haptics.light();
		void actionSheetAsync(threadTitle || "Задача", [
			{
				text: "Переименовать",
				onPress: () => {
					void promptAsync("Название задачи", {
						initialValue: threadTitle ?? "",
						acceptLabel: "Сохранить",
					}).then((next) => {
						if (!next) return;
						aui.threads.item("main").rename(next);
						haptics.success();
					});
				},
			},
			{
				text: "В архив",
				onPress: () => void aui.threads.item("main").archive(),
			},
			{
				text: "Удалить задачу",
				style: "destructive",
				onPress: () => void aui.threads.item("main").delete(),
			},
			{ text: "Отмена", style: "cancel" },
		]);
	};

	const refresh = () => {
		haptics.selection();
		void aui.threads.reload();
	};

	return (
		<View style={styles.root}>
			<View style={styles.leftSlot}>
				<CircleButton
					accessibilityLabel="Открыть меню"
					accessibilityRole="button"
					onPress={openDrawer}
				>
					<HamburgerMark />
				</CircleButton>
			</View>

			{isEmpty ? (
				<Pressable
					accessibilityLabel="Обновить"
					accessibilityRole="button"
					onPress={refresh}
					style={({ pressed }) => [
						styles.refresh,
						pressed && styles.pressed,
					]}
				>
					<Icon name="agent" size={20} color={colors.send} />
					<Text style={[styles.refreshText, { color: colors.send }]}>
						Обновить
					</Text>
				</Pressable>
			) : (
				<View style={styles.titleWrap}>
					<Text
						numberOfLines={1}
						style={[styles.activeTitle, { color: colors.mutedForeground }]}
					>
						{threadTitle ?? "Чат"}
					</Text>
				</View>
			)}

			{isEmpty ? (
				<View style={styles.rightSlot}>
					<CircleButton
						accessibilityLabel="История"
						accessibilityRole="button"
						onPress={openDrawer}
					>
						<Icon name="history" size={24} color={colors.foreground} />
					</CircleButton>
				</View>
			) : (
				<View
					accessibilityLabel="Действия с задачей"
					style={[
						styles.actionCapsule,
						{ backgroundColor: colors.surface, borderColor: colors.border },
					]}
				>
					<Pressable
						accessibilityHint={
							isRunning ? "Недоступно во время ответа" : "Переименовать задачу"
						}
						accessibilityLabel="Редактировать задачу"
						accessibilityRole="button"
						disabled={isRunning}
						hitSlop={5}
						onPress={() => {
							haptics.selection();
							void promptAsync("Название задачи", {
								initialValue: threadTitle ?? "",
								acceptLabel: "Сохранить",
							}).then((next) => {
								if (!next) return;
								aui.threads.item("main").rename(next);
								haptics.success();
							});
						}}
						style={({ pressed }) => [
							styles.capsuleButton,
							pressed && styles.pressed,
							isRunning && styles.disabled,
						]}
					>
						<Icon name="compose" size={19} color={colors.foreground} />
					</Pressable>
					<View style={[styles.capsuleDivider, { backgroundColor: colors.border }]} />
					<Pressable
						accessibilityLabel="Ещё действия"
						accessibilityRole="button"
						hitSlop={5}
						onPress={overflow}
						style={({ pressed }) => [
							styles.capsuleButton,
							pressed && styles.pressed,
						]}
					>
						<Icon name="more" size={20} color={colors.foreground} />
					</Pressable>
				</View>
			)}
		</View>
	);
}

const styles = StyleSheet.create({
	root: {
		alignItems: "center",
		flexDirection: "row",
		height: 76,
		paddingHorizontal: Layout.edgeInset,
	},
	leftSlot: { width: Layout.headerControl },
	rightSlot: { width: Layout.headerControl },
	titleWrap: {
		alignItems: "center",
		flex: 1,
		flexDirection: "row",
		gap: Spacing.xs,
		justifyContent: "center",
		minHeight: 40,
	},
	title: {
		fontSize: FontSize.text,
		fontWeight: FontWeight.semibold,
		letterSpacing: LetterSpacing.base,
	},
	refresh: {
		alignItems: "center",
		flex: 1,
		flexDirection: "row",
		gap: Spacing.sm,
		justifyContent: "center",
		minHeight: 40,
		paddingHorizontal: Spacing.lg,
	},
	refreshText: {
		fontSize: FontSize.text,
		fontWeight: FontWeight.bold,
		textDecorationLine: "underline",
	},
	activeTitle: {
		fontSize: FontSize.medium,
		fontWeight: FontWeight.semibold,
		letterSpacing: LetterSpacing.relaxed,
	},
	actionCapsule: {
		alignItems: "center",
		borderRadius: Radius.bubble,
		borderWidth: StyleSheet.hairlineWidth,
		flexDirection: "row",
		height: 40,
		paddingHorizontal: Spacing.xs,
	},
	capsuleButton: {
		alignItems: "center",
		borderRadius: Radius.controlSmall,
		height: 34,
		justifyContent: "center",
		width: 34,
	},
	capsuleDivider: { height: 22, width: StyleSheet.hairlineWidth },
	pressed: { opacity: 0.55 },
	disabled: { opacity: 0.42 },
});

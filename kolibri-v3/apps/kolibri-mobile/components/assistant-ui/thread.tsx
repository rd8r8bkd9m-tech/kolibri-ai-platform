import { ThreadPrimitive } from "@assistant-ui/react-native";
import { useDrawerStatus } from "expo-router/drawer";
import {
	KeyboardAvoidingView,
	Platform,
	StyleSheet,
	Text,
	View,
} from "react-native";

import { Composer } from "@/components/assistant-ui/composer";
import { MessageBubble } from "@/components/assistant-ui/message";
import { PetMiniAssistant } from "@/components/pet/pet-mini-assistant";
import { Icon } from "@/components/ui/icon";
import { Layout } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";

const starters = [
	{
		label: "Начать задачу",
		prompt: "Помоги разобраться с новой задачей",
		icon: "bubble" as const,
	},
	{
		label: "Написать или отредактировать",
		prompt: "Помоги написать или отредактировать документ",
		icon: "compose" as const,
	},
	{
		label: "Искать в справочниках",
		prompt: "Найди информацию в доступных справочниках",
		icon: "search" as const,
	},
];

function EmptyState() {
	const { colors } = useTheme();
	return (
		<View style={styles.empty}>
			<View style={styles.emptySpacer} />
			<View accessibilityLabel="Быстрые действия" style={styles.starters}>
				{starters.map((starter) => (
					<ThreadPrimitive.Suggestion
						key={starter.label}
						accessibilityRole="button"
						onPressIn={haptics.selection}
						prompt={starter.prompt}
						send
						style={({ pressed }: { pressed: boolean }) => [
							styles.starter,
							pressed && styles.pressed,
						]}
					>
						<Icon
							name={starter.icon}
							size={21}
							color={colors.mutedForeground}
						/>
						<Text
							numberOfLines={2}
							style={[styles.starterText, { color: colors.mutedForeground }]}
						>
							{starter.label}
						</Text>
					</ThreadPrimitive.Suggestion>
				))}
			</View>
		</View>
	);
}

function Messages() {
	return (
		<>
			<ThreadPrimitive.Empty>
				<EmptyState />
			</ThreadPrimitive.Empty>
			<ThreadPrimitive.If empty={false}>
				<ThreadPrimitive.MessagesFlatList
					contentContainerStyle={styles.messageList}
					keyboardDismissMode="interactive"
					keyboardShouldPersistTaps="handled"
					showsVerticalScrollIndicator={false}
					style={styles.flex}
				>
					{() => <MessageBubble />}
				</ThreadPrimitive.MessagesFlatList>
			</ThreadPrimitive.If>
		</>
	);
}

export function Thread() {
	const { colors } = useTheme();
	const drawerOpen = useDrawerStatus() === "open";
	return (
		<KeyboardAvoidingView
			behavior={Platform.OS === "ios" ? "padding" : undefined}
			style={[styles.root, { backgroundColor: colors.background }]}
		>
			<View style={styles.flex}>
				<Messages />
			</View>
			{drawerOpen ? null : (
				<>
					<PetMiniAssistant />
					<Composer />
				</>
			)}
		</KeyboardAvoidingView>
	);
}

const styles = StyleSheet.create({
	// RN Web maps the chat list to a CSS flex child. Without an explicit
	// min-height of zero, the child can refuse to shrink and gestures are sent
	// to the page/drawer instead of the list once a conversation grows.
	root: { flex: 1, minHeight: 0, minWidth: 0 },
	flex: { flex: 1, minHeight: 0, minWidth: 0 },
	empty: {
		flex: 1,
		paddingBottom: 8,
		paddingHorizontal: Layout.edgeInset + 12,
	},
	emptySpacer: { flex: 1 },
	starters: { gap: 17, paddingBottom: 8 },
	starter: {
		alignItems: "center",
		flexDirection: "row",
		gap: 14,
		minHeight: 36,
	},
	starterText: {
		flex: 1,
		fontSize: 18,
		fontWeight: "600",
		letterSpacing: -0.35,
		lineHeight: 23,
	},
	pressed: { opacity: 0.55 },
	messageList: {
		alignSelf: "center",
		gap: 18,
		flexGrow: 1,
		maxWidth: Layout.threadMaxWidth,
		paddingHorizontal: 14,
		paddingVertical: 20,
		width: "100%",
	},
});

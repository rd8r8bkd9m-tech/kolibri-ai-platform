import {
	AuiIf,
	ThreadPrimitive,
	type ThreadMessage,
	useAuiEvent,
	useAuiState,
} from "@assistant-ui/react-native";
import { useDrawerStatus } from "expo-router/drawer";
import { useCallback, useEffect, useRef, useState } from "react";
import {
	FlatList,
	KeyboardAvoidingView,
	NativeScrollEvent,
	NativeSyntheticEvent,
	Platform,
	Pressable,
	StyleSheet,
	Text,
	View,
} from "react-native";

import { Composer } from "@/components/assistant-ui/composer";
import { MessageBubble } from "@/components/assistant-ui/message";
import { Icon } from "@/src/components/icons/Icon";
import {
	Layout,
	LetterSpacing,
	LineHeight,
	Radius,
	Spacing,
	WebShadow,
	shadow,
	typography,
} from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";

const starters = [
	{
		label: "Создать изображение",
		prompt:
			"Создай изображение по моему описанию. Сначала уточни стиль, формат и назначение.",
		icon: "image" as const,
		send: true,
	},
	{
		label: "Написать или отредактировать",
		prompt:
			"Помоги написать или отредактировать текст. Сначала уточни тип текста, аудиторию и желаемый результат.",
		icon: "compose" as const,
		send: false,
	},
	{
		label: "Искать в интернете",
		prompt:
			"Найди актуальную информацию в интернете по моему запросу и приложи источники.",
		icon: "globe" as const,
		send: false,
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
						send={starter.send}
						clearComposer={starter.send}
						style={({ pressed }: { pressed: boolean }) => [
							styles.starter,
							pressed && styles.pressed,
						]}
					>
						<Icon
							name={starter.icon}
							size={26}
							color={colors.mutedForeground}
						/>
						<Text
							numberOfLines={2}
							style={[
								typography.suggest,
								styles.starterText,
								{ color: colors.mutedForeground },
							]}
						>
							{starter.label}
						</Text>
					</ThreadPrimitive.Suggestion>
				))}
			</View>
		</View>
	);
}

function Messages({ drawerOpen }: { drawerOpen: boolean }) {
	const { colors } = useTheme();
	const listRef = useRef<FlatList<ThreadMessage>>(null);
	const [showScrollToBottom, setShowScrollToBottom] = useState(false);
	const threadId = useAuiState((state) => state.threads.mainThreadId);
	const messages = useAuiState((state) => state.thread.messages);
	const lastMessageRoleRef = useRef<string | null>(null);
	const atBottomRef = useRef(true);
	const forceScrollToBottomRef = useRef(false);
	useEffect(() => {
		lastMessageRoleRef.current = messages[messages.length - 1]?.role;
	}, [messages]);
	useAuiEvent("thread.runStart", () => {
		forceScrollToBottomRef.current = true;
	});
	const scrollToBottom = useCallback((animated = false) => {
		atBottomRef.current = true;
		const list = listRef.current;
		if (!list) return;
		if (Platform.OS === "web") {
			const node = (
				list as unknown as {
					getScrollableNode?: () => HTMLElement | null;
				}
			).getScrollableNode?.();
			if (node) {
				node.scrollTop = node.scrollHeight;
				return;
			}
		}
		list.scrollToEnd({ animated });
	}, []);
	useEffect(() => {
		atBottomRef.current = true;
		requestAnimationFrame(() => {
			scrollToBottom(false);
		});
	}, [scrollToBottom, threadId]);
	const handleScroll = useCallback(
		(event: NativeSyntheticEvent<NativeScrollEvent>) => {
			const { contentOffset, contentSize, layoutMeasurement } =
				event.nativeEvent;
			const distanceFromBottom =
				contentSize.height - (contentOffset.y + layoutMeasurement.height);
			atBottomRef.current = distanceFromBottom <= 140;
			const shouldShow = distanceFromBottom > 140;
			setShowScrollToBottom((current) =>
				current === shouldShow ? current : shouldShow,
			);
		},
		[],
	);
	const handleContentSizeChange = useCallback(() => {
		if (
			!atBottomRef.current &&
			!forceScrollToBottomRef.current &&
			lastMessageRoleRef.current !== "user"
		) {
			return;
		}
		forceScrollToBottomRef.current = false;
		requestAnimationFrame(() => {
			requestAnimationFrame(() => {
				atBottomRef.current = true;
				scrollToBottom(false);
			});
		});
	}, [scrollToBottom]);

	return (
		<>
			<AuiIf condition={(state) => state.thread.isEmpty}>
				<EmptyState />
			</AuiIf>
			<AuiIf condition={(state) => !state.thread.isEmpty}>
				<ThreadPrimitive.MessagesFlatList
					autoScroll={false}
					contentContainerStyle={styles.messageList}
					keyboardDismissMode="interactive"
					keyboardShouldPersistTaps="handled"
					onContentSizeChange={handleContentSizeChange}
					onScroll={handleScroll}
					ref={listRef}
					scrollEventThrottle={120}
					scrollToBottomOnInitialize={false}
					scrollToBottomOnRunStart={false}
					scrollToBottomOnThreadSwitch={false}
					showsVerticalScrollIndicator={false}
					style={styles.flex}
				>
					{() => <MessageBubble />}
				</ThreadPrimitive.MessagesFlatList>
			</AuiIf>
			{!drawerOpen && showScrollToBottom ? (
			<Pressable
				accessibilityLabel="Прокрутить вниз"
				accessibilityRole="button"
				onPress={() => {
					atBottomRef.current = true;
					scrollToBottom(true);
				}}
				style={({ pressed }) => [
					styles.scrollToBottom,
					{
						backgroundColor: colors.surfaceRaised,
						borderColor: colors.border,
					},
					Platform.select({
						web: {
							boxShadow: WebShadow.floating,
						} as never,
						ios: {
							shadowColor: shadow.shadowColor,
							shadowOffset: { height: 2, width: 0 },
							shadowOpacity: 0.18,
							shadowRadius: 8,
						},
						default: { elevation: 4 },
					}),
					pressed && styles.pressed,
				]}
			>
					<Icon name="chevron-down" size={18} color={colors.foreground} />
				</Pressable>
			) : null}
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
				<Messages drawerOpen={drawerOpen} />
			</View>
			{drawerOpen ? null : (
				<>
					<Composer />
				</>
			)}
		</KeyboardAvoidingView>
	);
}

const styles = StyleSheet.create({
	root: { flex: 1, minHeight: 0, minWidth: 0 },
	flex: { flex: 1, minHeight: 0, minWidth: 0, position: "relative" },
	empty: {
		flex: 1,
		paddingBottom: Spacing.sm,
		paddingHorizontal: Spacing.xxl,
	},
	emptySpacer: { flex: 1 },
	starters: { gap: Spacing.xxl, paddingBottom: Spacing.sm },
	starter: {
		alignItems: "center",
		flexDirection: "row",
		gap: Spacing.lg,
		minHeight: 44,
	},
	starterText: {
		flex: 1,
		letterSpacing: LetterSpacing.small,
		lineHeight: LineHeight.screen,
	},
	pressed: { opacity: 0.55 },
	scrollToBottom: {
		alignItems: "center",
		borderRadius: Radius.input,
		borderWidth: StyleSheet.hairlineWidth,
		bottom: Spacing.lg,
		height: 32,
		justifyContent: "center",
		position: "absolute",
		right: Layout.composerInset,
		width: 32,
	},
	messageList: {
		alignSelf: "center",
		gap: Layout.composerInset,
		flexGrow: 1,
		maxWidth: Layout.threadMaxWidth,
		paddingHorizontal: Spacing.lg,
		paddingVertical: Spacing.xl,
		width: "100%",
	},
});

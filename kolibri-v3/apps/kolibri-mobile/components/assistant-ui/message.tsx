import {
	AuiIf,
	ErrorPrimitive,
	MessagePrimitive,
	ThreadPrimitive,
	type ImageMessagePartComponent,
	type ToolCallMessagePartComponent,
	useAuiState,
	type TextMessagePartComponent,
} from "@assistant-ui/react-native";
import { useEffect, useState } from "react";
import {
	Animated,
	Image,
	Platform,
	Pressable,
	StyleSheet,
	Text,
	View,
} from "react-native";
import { useReducedMotion } from "react-native-reanimated";

import { MessageActionBar } from "@/components/assistant-ui/message-action-bar";
import { MessageBranchPicker } from "@/components/assistant-ui/message-branch-picker";
import { DataCardFallback } from "@/components/assistant-ui/cards/data-card-fallback";
import { ImageGenerationCard } from "@/components/assistant-ui/cards/image-generation-card";
import { WeatherCard } from "@/components/assistant-ui/cards/weather-card";
import { EstimateWidgetCard } from "@/components/assistant-ui/estimate-widget-card";
import { EstimateGenerationActivityCard } from "@/components/assistant-ui/estimate-generation-activity-card";
import {
	FontSize,
	FontWeight,
	LetterSpacing,
	LineHeight,
	Radius,
	Spacing,
} from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";
import { DATA_PART_NAMES } from "@/src/product-chat/cards";
import {
	parseEstimateEditorWidget,
	parseEstimateGenerationActivity,
} from "@/src/product-chat/estimate-widget";

const UserText: TextMessagePartComponent = ({ text }) => {
	const { colors } = useTheme();
	return (
		<Text style={[styles.userText, { color: colors.foreground }]}>{text}</Text>
	);
};

const AssistantText: TextMessagePartComponent = ({ text }) => {
	const { colors } = useTheme();
	return (
		<Text
			selectable
			style={[styles.assistantText, { color: colors.foreground }]}
		>
			{text}
		</Text>
	);
};

const AssistantImage: ImageMessagePartComponent = ({ image }) => {
	const { colors } = useTheme();
	return (
		<Image
			accessibilityLabel="Изображение из ответа"
			resizeMode="cover"
			source={{ uri: image }}
			style={[styles.resultImage, { backgroundColor: colors.muted }]}
		/>
	);
};

const EstimateToolCall: ToolCallMessagePartComponent = ({ args }) => {
	const widget = parseEstimateEditorWidget(args);
	if (widget) {
		return <EstimateWidgetCard widget={widget} />;
	}
	const activity = parseEstimateGenerationActivity(args);
	if (activity) {
		return <EstimateGenerationActivityCard widget={activity} />;
	}
	return null;
};

function ReasoningBlock({ text }: { text: string }) {
	const { colors } = useTheme();
	const [open, setOpen] = useState(false);
	const content = text?.trim();
	if (!content) return null;
	return (
		<View
			style={[
				styles.reasoning,
				{
					backgroundColor: colors.surface,
					borderColor: colors.border,
				},
			]}
		>
			<Pressable
				accessibilityLabel="Рассуждение"
				accessibilityRole="button"
				accessibilityState={{ expanded: open }}
				onPress={() => {
					haptics.selection();
					setOpen((value) => !value);
				}}
				style={styles.reasoningHeader}
			>
				<Text style={[styles.reasoningTitle, { color: colors.mutedForeground }]}>
					Рассуждение
				</Text>
				<Text style={[styles.reasoningChevron, { color: colors.mutedForeground }]}>
					{open ? "⌃" : "⌄"}
				</Text>
			</Pressable>
			{open ? (
				<View style={[styles.reasoningBody, { borderTopColor: colors.border }]}>
					<Text
						selectable
						style={[styles.reasoningText, { color: colors.mutedForeground }]}
					>
						{content}
					</Text>
				</View>
			) : null}
		</View>
	);
}

function TypingDot({ delay }: { delay: number }) {
	const { colors } = useTheme();
	const reduceMotion = useReducedMotion();
	const [opacity] = useState(() => new Animated.Value(0.28));

	useEffect(() => {
		if (reduceMotion) {
			opacity.setValue(0.9);
			return;
		}
		const animation = Animated.loop(
			Animated.sequence([
				Animated.timing(opacity, {
					toValue: 1,
					duration: 380,
					delay,
					useNativeDriver: Platform.OS !== "web",
				}),
				Animated.timing(opacity, {
					toValue: 0.28,
					duration: 380,
					useNativeDriver: Platform.OS !== "web",
				}),
			]),
		);
		animation.start();
		return () => animation.stop();
	}, [delay, opacity, reduceMotion]);

	return (
		<Animated.View
			style={[styles.dot, { backgroundColor: colors.mutedForeground, opacity }]}
		/>
	);
}

function TypingIndicator() {
	const running = useAuiState(
		(state) => state.message.status?.type === "running",
	);
	if (!running) return null;
	return (
		<View accessibilityLabel="Kolibri формирует ответ" style={styles.typing}>
			<TypingDot delay={0} />
			<TypingDot delay={140} />
			<TypingDot delay={280} />
		</View>
	);
}

function UserMessage() {
	const { colors } = useTheme();
	return (
		<MessagePrimitive.Root style={styles.userRoot}>
			<View style={[styles.userBubble, { backgroundColor: colors.userBubble }]}>
				<MessagePrimitive.Parts components={{ Text: UserText }} />
			</View>
			<MessageBranchPicker align="flex-end" />
		</MessagePrimitive.Root>
	);
}

function AssistantMessage() {
	const { colors } = useTheme();
	const suggestions = useAuiState((state) => state.thread.suggestions);
	return (
		<MessagePrimitive.Root style={styles.assistantRoot}>
			<View style={styles.assistantContent}>
				<MessagePrimitive.Parts
					components={{
						Text: AssistantText,
						Image: AssistantImage,
						Reasoning: ReasoningBlock,
						Empty: TypingIndicator,
						tools: {
							Override: EstimateToolCall,
						},
						data: {
							by_name: {
								[DATA_PART_NAMES.weather]: ({ data }) => (
									<WeatherCard data={data} />
								),
								[DATA_PART_NAMES.imageGeneration]: ({ data }) => (
									<ImageGenerationCard data={data} />
								),
							},
							Fallback: ({ name }) => <DataCardFallback name={name} />,
						},
					}}
				/>
				<ErrorPrimitive.Root
					style={[
						styles.error,
						{
							backgroundColor: colors.destructiveSurface,
							borderColor: colors.destructive,
						},
					]}
				>
					<ErrorPrimitive.Message
						style={[styles.errorText, { color: colors.destructive }]}
					/>
				</ErrorPrimitive.Root>
			</View>
			<AuiIf condition={(state) => state.message.status?.type !== "running"}>
				<View style={styles.actions}>
					<MessageBranchPicker />
					<MessageActionBar />
				</View>
				{suggestions.length > 0 ? (
					<View
						accessibilityLabel="Варианты продолжения"
						style={styles.suggestions}
					>
						{suggestions.map((suggestion, index) => (
							<ThreadPrimitive.Suggestion
								key={index}
								accessibilityRole="button"
								onPressIn={haptics.selection}
								prompt={suggestion.prompt}
								send
								clearComposer
								style={({ pressed }: { pressed: boolean }) => [
									styles.suggestion,
									{
										backgroundColor: colors.surface,
										borderColor: colors.border,
									},
									pressed && styles.pressed,
								]}
							>
								<Text
									numberOfLines={2}
									style={[styles.suggestionText, { color: colors.foreground }]}
								>
									{suggestion.prompt}
								</Text>
							</ThreadPrimitive.Suggestion>
						))}
					</View>
				) : null}
			</AuiIf>
		</MessagePrimitive.Root>
	);
}

export function MessageBubble() {
	const role = useAuiState((state) => state.message.role);
	return role === "user" ? <UserMessage /> : <AssistantMessage />;
}

const styles = StyleSheet.create({
	userRoot: { alignItems: "flex-end" },
	userBubble: {
		borderRadius: Radius.bubble,
		maxWidth: "86%",
		paddingHorizontal: Spacing.lg,
		paddingVertical: Spacing.md,
	},
	assistantRoot: { alignItems: "flex-start" },
	assistantContent: { paddingHorizontal: Spacing.xs },
	reasoning: {
		borderRadius: Radius.md,
		borderWidth: StyleSheet.hairlineWidth,
		marginBottom: Spacing.md,
		marginTop: Spacing.xs,
		overflow: "hidden",
	},
	reasoningHeader: {
		alignItems: "center",
		flexDirection: "row",
		justifyContent: "space-between",
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.md,
	},
	reasoningTitle: {
		fontSize: FontSize.footnote,
		fontWeight: FontWeight.semibold,
		lineHeight: LineHeight.footnote,
	},
	reasoningChevron: { fontSize: FontSize.body, lineHeight: LineHeight.footnote },
	reasoningBody: {
		borderTopWidth: StyleSheet.hairlineWidth,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.md,
	},
	reasoningText: { fontSize: FontSize.footnote, lineHeight: LineHeight.small },
	userText: {
		fontSize: FontSize.text,
		letterSpacing: LetterSpacing.relaxed,
		lineHeight: LineHeight.relaxed,
	},
	assistantText: {
		fontSize: FontSize.text,
		letterSpacing: LetterSpacing.relaxed,
		lineHeight: LineHeight.text,
	},
	resultImage: {
		borderRadius: Radius.card,
		height: 220,
		maxWidth: 300,
		width: "100%",
	},
	typing: {
		alignItems: "center",
		flexDirection: "row",
		gap: Spacing.xs,
		paddingVertical: Spacing.md,
	},
	dot: { borderRadius: Radius.dot, height: 7, width: 7 },
	actions: {
		alignItems: "center",
		flexDirection: "row",
		gap: Spacing.xs,
		marginLeft: -Spacing.xs,
		marginTop: Spacing.sm,
	},
	error: {
		borderRadius: Radius.md,
		borderWidth: StyleSheet.hairlineWidth,
		marginTop: Spacing.sm,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.md,
	},
	suggestions: {
		flexDirection: "row",
		flexWrap: "wrap",
		gap: Spacing.sm,
		marginTop: Spacing.md,
	},
	suggestion: {
		borderRadius: Radius.circle,
		borderWidth: StyleSheet.hairlineWidth,
		maxWidth: "92%",
		paddingHorizontal: Spacing.lg,
		paddingVertical: Spacing.sm,
	},
	suggestionText: {
		fontSize: FontSize.footnote,
		fontWeight: FontWeight.semibold,
		lineHeight: LineHeight.footnote,
	},
	pressed: { opacity: 0.6 },
	errorText: { fontSize: FontSize.small, lineHeight: LineHeight.normal },
});

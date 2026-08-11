import {
	AuiIf,
	ComposerPrimitive,
	AttachmentPrimitive,
	useAui,
} from "@assistant-ui/react-native";
import * as DocumentPicker from "expo-document-picker";
import {
	ActivityIndicator,
	Platform,
	Pressable,
	ScrollView,
	StyleSheet,
	Text,
	View,
} from "react-native";
import { useCallback, useState } from "react";

import { Icon } from "@/components/ui/icon";
import { Layout } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";
import { API_BASE_URL } from "@/src/auth/mobile-session";
import { useProductChatContext } from "@/src/product-chat/runtime-provider";

// Contract marker for the behavioral QA: the PWA Enter-to-send behaviour is
// only testable once the served bundle contains this module. The dev server
// can briefly serve a stale cached bundle after a hot edit, so the QA waits
// for this flag before interacting instead of racing Metro.
if (typeof globalThis !== "undefined") {
	(globalThis as { __KOLIBRI_MOBILE_ENTER_SEND__?: boolean })
		.__KOLIBRI_MOBILE_ENTER_SEND__ = true;
}

function ComposerAttachments() {
	const { colors } = useTheme();
	return (
		<ComposerPrimitive.Attachments>
			{({ attachment }) => (
				<View style={[styles.attachmentChip, { backgroundColor: colors.muted }]}>
					<Icon name="document" size={16} color={colors.foreground} />
					<AttachmentPrimitive.Name
						numberOfLines={1}
						style={[styles.attachmentName, { color: colors.foreground }]}
					/>
					<AttachmentPrimitive.Remove
						accessibilityLabel={`Удалить ${attachment.name}`}
						style={styles.attachmentRemove}
					>
						<Icon name="close" size={14} color={colors.mutedForeground} />
					</AttachmentPrimitive.Remove>
				</View>
			)}
		</ComposerPrimitive.Attachments>
	);
}

function AttachmentButton() {
	const aui = useAui();
	const { colors } = useTheme();
	const { activeProjectId, activeThreadId, attachmentClient } =
		useProductChatContext();
	const [busy, setBusy] = useState(false);
	const canAttach = Boolean(activeProjectId && activeThreadId) && !busy;

	const pick = async () => {
		if (!activeProjectId || !activeThreadId || busy) return;
		haptics.selection();
		setBusy(true);
		try {
			const capability = await attachmentClient.capability(
				activeProjectId,
				activeThreadId,
			);
			const result = await DocumentPicker.getDocumentAsync({
				copyToCacheDirectory: true,
				multiple: true,
				type: capability.accept,
			});
			if (result.canceled) return;
			for (const asset of result.assets.slice(0, capability.maxAttachmentsPerMessage)) {
				const uploaded = await attachmentClient.upload(capability, asset);
				await aui.composer.addAttachment({
					id: uploaded.attachmentId,
					type: uploaded.mimeType.startsWith("image/") ? "image" : "document",
					name: uploaded.filename,
					contentType: uploaded.mimeType,
					content: [
						{
							type: "file",
							data: `${API_BASE_URL}${uploaded.contentPath}`,
							mimeType: uploaded.mimeType,
							filename: uploaded.filename,
						},
					],
				});
			}
		} catch (error) {
			if (__DEV__) console.warn("[Kolibri Mobile] attachment failed", error);
		} finally {
			setBusy(false);
		}
	};

	return (
		<Pressable
			accessibilityHint={
				canAttach
					? "Открывает выбор файлов"
					: "Сначала отправьте сообщение, чтобы создать задачу"
			}
			accessibilityLabel="Добавить вложение"
			accessibilityRole="button"
			accessibilityState={{ disabled: !canAttach, busy }}
			disabled={!canAttach}
			onPress={pick}
			style={[styles.plus, !canAttach && styles.disabled]}
		>
			{busy ? (
				<ActivityIndicator color={colors.foreground} size="small" />
			) : (
				<Icon name="plus" size={28} color={colors.foreground} />
			)}
		</Pressable>
	);
}

function SendButton() {
	const { colors } = useTheme();
	return (
		<ComposerPrimitive.Send
			accessibilityLabel="Отправить"
			onPressIn={haptics.success}
			style={[styles.action, { backgroundColor: colors.foreground }]}
		>
			<Icon
				name="send"
				size={21}
				color={colors.background}
				weight="semibold"
			/>
		</ComposerPrimitive.Send>
	);
}

function StopButton() {
	const { colors } = useTheme();
	return (
		<ComposerPrimitive.Cancel
			accessibilityLabel="Остановить ответ"
			onPressIn={haptics.light}
			style={[styles.action, { backgroundColor: colors.foreground }]}
		>
			<Icon name="stop" size={15} color={colors.background} />
		</ComposerPrimitive.Cancel>
	);
}

export function Composer() {
	const { colors } = useTheme();
	const aui = useAui();
	const [focused, setFocused] = useState(false);
	const handleFocus = useCallback(() => setFocused(true), []);
	const handleBlur = useCallback(() => setFocused(false), []);
	// Desktop chat sends on Enter (enterKeyHint="send"); keep the same
	// behavior in the PWA. Shift+Enter still inserts a newline. The native
	// multiline input keeps the send button as the primary action.
	const handleKeyPress = useCallback(
		(event: { nativeEvent: { key?: string; shiftKey?: boolean }; preventDefault: () => void }) => {
			if (Platform.OS !== "web") return;
			if (event.nativeEvent.key === "Enter" && !event.nativeEvent.shiftKey) {
				event.preventDefault();
				// The keydown can arrive before the last onChange propagated to
				// the composer store, which would make send() a no-op. Read the
				// value straight from the DOM target and sync it first.
				const target = (
					event as unknown as { target?: { value?: string } }
				).target;
				if (typeof target?.value === "string" && target.value.trim()) {
					aui.composer.setText(target.value);
				}
				aui.composer.send();
			}
		},
		[aui],
	);
	return (
		<View style={styles.outer}>
			<ScrollView
				horizontal
				contentContainerStyle={styles.attachments}
				showsHorizontalScrollIndicator={false}
			>
				<ComposerAttachments />
			</ScrollView>
			<ComposerPrimitive.Root
				style={[
					styles.root,
					{
						backgroundColor: colors.composer,
					},
					focused && styles.focusedShadow,
				]}
			>
				<AttachmentButton />
				<ComposerPrimitive.Input
					accessibilityLabel="Сообщение"
					maxLength={65_536}
					multiline
					onBlur={handleBlur}
					onFocus={handleFocus}
					onKeyPress={handleKeyPress}
					placeholder="Спросить Kolibri…"
					placeholderTextColor={colors.mutedForeground}
					style={[styles.input, { color: colors.foreground }]}
				/>
				<AuiIf condition={(state) => !state.thread.isRunning}>
					<AuiIf condition={(state) => !state.composer.isEmpty}>
						<SendButton />
					</AuiIf>
				</AuiIf>
				<AuiIf condition={(state) => state.thread.isRunning}>
					<StopButton />
				</AuiIf>
			</ComposerPrimitive.Root>
			<Text
				style={[styles.disclaimer, { color: colors.mutedForeground }]}
			>
				Kolibri может ошибаться. Проверяйте важные данные.
			</Text>
		</View>
	);
}

const styles = StyleSheet.create({
	outer: {
		alignSelf: "center",
		maxWidth: Layout.threadMaxWidth + 24,
		paddingHorizontal: Layout.edgeInset,
		paddingTop: 8,
		width: "100%",
	},
	attachments: { gap: 6, paddingBottom: 6 },
	attachmentChip: {
		alignItems: "center",
		borderRadius: 12,
		flexDirection: "row",
		gap: 5,
		maxWidth: 220,
		paddingHorizontal: 9,
		paddingVertical: 6,
	},
	attachmentName: { flexShrink: 1, fontSize: 13, fontWeight: "600" },
	attachmentRemove: { alignItems: "center", height: 22, justifyContent: "center", width: 22 },
	root: {
		alignItems: "flex-end",
		borderRadius: 32,
		borderWidth: 0,
		flexDirection: "row",
		minHeight: 58,
		padding: 6,
		...Platform.select({
			web: {
				boxShadow:
					"0 12px 36px -24px rgba(0, 0, 0, 0.45), 0 2px 8px -4px rgba(0, 0, 0, 0.12)",
			} as never,
			ios: {
				shadowColor: "#000",
				shadowOffset: { height: 4, width: 0 },
				shadowOpacity: 0.12,
				shadowRadius: 18,
			},
			default: {
				elevation: 5,
			},
		}),
	},
	focusedShadow: {
		...Platform.select({
			web: {
				boxShadow:
					"0 16px 40px -24px rgba(0, 0, 0, 0.5), 0 3px 10px -4px rgba(0, 0, 0, 0.14)",
			} as never,
			ios: {
				shadowOpacity: 0.18,
				shadowRadius: 22,
			},
			default: {},
		}),
	},
	plus: {
		alignItems: "center",
		height: 40,
		justifyContent: "center",
		opacity: 0.94,
		width: 40,
	},
	disabled: { opacity: 0.42 },
	input: {
		flex: 1,
		fontSize: 16,
		lineHeight: 22,
		maxHeight: 180,
		minHeight: 40,
		paddingBottom: 9,
		paddingHorizontal: 7,
		paddingTop: 9,
		...Platform.select({
			web: { outlineStyle: "none" } as never,
			default: {},
		}),
	},
	action: {
		alignItems: "center",
		borderRadius: 22,
		height: 44,
		justifyContent: "center",
		width: 44,
	},
	disclaimer: {
		fontSize: 12,
		lineHeight: 16,
		paddingBottom: 6,
		paddingTop: 7,
		textAlign: "center",
	},
});

import {
	AuiIf,
	ComposerPrimitive,
	AttachmentPrimitive,
	useAui,
	useAuiState,
} from "@assistant-ui/react-native";
import * as DocumentPicker from "expo-document-picker";
import {
	ActivityIndicator,
	Platform,
	Pressable,
	ScrollView,
	StyleSheet,
	View,
} from "react-native";
import { useState } from "react";

import { Icon } from "@/components/ui/icon";
import { Layout, Radius } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";
import { API_BASE_URL } from "@/src/auth/mobile-session";
import { useProductChatContext } from "@/src/product-chat/runtime-provider";

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
	const canSend = useAuiState((state) => state.composer.canSend);
	return (
		<ComposerPrimitive.Send
			accessibilityLabel="Отправить"
			onPressIn={() => canSend && haptics.success()}
			style={[
				styles.action,
				{ backgroundColor: canSend ? "#0a84ff" : "#4b4b4b" },
			]}
		>
			<Icon name="send" size={20} color="#ffffff" weight="semibold" />
		</ComposerPrimitive.Send>
	);
}

function StopButton() {
	return (
		<ComposerPrimitive.Cancel
			accessibilityLabel="Остановить ответ"
			onPressIn={haptics.light}
			style={[styles.action, { backgroundColor: "#0a84ff" }]}
		>
			<Icon name="stop" size={15} color="#ffffff" />
		</ComposerPrimitive.Cancel>
	);
}

export function Composer() {
	const { colors } = useTheme();
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
					{ backgroundColor: colors.composer, borderColor: colors.border },
				]}
			>
				<AttachmentButton />
				<ComposerPrimitive.Input
					accessibilityLabel="Сообщение"
					maxLength={65_536}
					multiline
					placeholder="Спросить Kolibri…"
					placeholderTextColor={colors.mutedForeground}
					style={[styles.input, { color: colors.foreground }]}
				/>
				<AuiIf condition={(state) => !state.thread.isRunning}>
					<SendButton />
				</AuiIf>
				<AuiIf condition={(state) => state.thread.isRunning}>
					<StopButton />
				</AuiIf>
			</ComposerPrimitive.Root>
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
		borderRadius: Radius.composer,
		borderWidth: StyleSheet.hairlineWidth,
		flexDirection: "row",
		minHeight: 54,
		padding: 6,
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
		maxHeight: 132,
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
		borderRadius: 21,
		height: 42,
		justifyContent: "center",
		width: 42,
	},
});

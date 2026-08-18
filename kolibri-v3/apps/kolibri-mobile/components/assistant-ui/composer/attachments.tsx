import {
	AttachmentPrimitive,
	ComposerPrimitive,
	useAui,
} from "@assistant-ui/react-native";
import * as DocumentPicker from "expo-document-picker";
import { ActivityIndicator, Pressable, StyleSheet, View } from "react-native";
import { useState } from "react";

import { Icon } from "@/src/components/icons/Icon";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";
import { API_BASE_URL } from "@/src/auth/mobile-session";
import { useProductChatContext } from "@/src/product-chat/runtime-provider";

import { styles } from "./styles";

const plusStyles = StyleSheet.create({
	button: {
		alignItems: "center",
		height: 32,
		justifyContent: "center",
		width: 32,
	},
});

export function ComposerAttachments() {
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

export function AttachmentButton() {
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
			hitSlop={6}
			onPress={pick}
			style={({ pressed }) => [
				plusStyles.button,
				!canAttach && styles.disabled,
				pressed && styles.pressed,
			]}
		>
			{busy ? (
				<ActivityIndicator color={colors.foreground} size="small" />
			) : (
				<Icon name="plus" size={26} color={colors.foreground} />
			)}
		</Pressable>
	);
}

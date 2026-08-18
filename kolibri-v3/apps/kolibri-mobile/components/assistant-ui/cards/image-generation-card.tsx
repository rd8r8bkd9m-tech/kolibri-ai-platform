import {
	ActivityIndicator,
	Image,
	Pressable,
	Share,
	StyleSheet,
	Text,
	View,
} from "react-native";

import { Icon } from "@/src/components/icons/Icon";
import { Radius } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";
import { parseImageGenerationCard } from "@/src/product-chat/cards";

export function ImageGenerationCard({ data }: { data: unknown }) {
	const { colors } = useTheme();
	const card = parseImageGenerationCard(data);
	if (!card) {
		return (
			<View
				accessibilityRole="alert"
				style={[
					styles.invalid,
					{
						backgroundColor: colors.destructiveSurface,
						borderColor: colors.destructive,
					},
				]}
			>
				<Text style={[styles.invalidText, { color: colors.destructive }]}>
					Не удалось прочитать карточку изображения
				</Text>
			</View>
		);
	}

	const share = async () => {
		if (!card.imageUrl) return;
		haptics.selection();
		try {
			await Share.share({
				message: card.prompt ?? "Изображение",
				url: card.imageUrl,
			});
		} catch {
			// Sharing can be cancelled by the user; nothing to surface.
		}
	};

	if (card.status === "generating") {
		return (
			<View
				accessibilityLabel="Изображение генерируется"
				style={[
					styles.skeleton,
					{ backgroundColor: colors.surface, borderColor: colors.border },
				]}
			>
				<ActivityIndicator color={colors.mutedForeground} />
				<Text style={[styles.thinking, { color: colors.mutedForeground }]}>
					Думаю…
				</Text>
			</View>
		);
	}

	return (
		<View style={styles.wrap}>
			{card.status === "preview" ? (
				<View
					accessibilityLabel="Предпросмотр изображения"
					style={[
						styles.preview,
						{ backgroundColor: colors.surface, borderColor: colors.border },
					]}
				>
					<View style={[styles.previewPill, { backgroundColor: colors.surfaceRaised }]}>
						<Text style={[styles.previewPillText, { color: colors.mutedForeground }]}>
							Предпросмотр
						</Text>
					</View>
					<View style={styles.thumbStrip}>
						{[0, 1, 2, 3].map((index) => {
							const thumbnail = card.thumbnails?.[index];
							return thumbnail ? (
								<Image
									key={index}
									source={{ uri: thumbnail }}
									style={[
										styles.thumb,
										{ backgroundColor: colors.muted, borderColor: colors.border },
									]}
								/>
							) : (
								<View
									key={index}
									style={[
										styles.thumb,
										styles.thumbPlaceholder,
										{ backgroundColor: colors.muted, borderColor: colors.border },
									]}
								/>
							);
						})}
					</View>
				</View>
			) : (
				<View style={styles.result}>
					{card.imageUrl ? (
						<Image
							accessibilityLabel={card.prompt ?? "Сгенерированное изображение"}
							source={{ uri: card.imageUrl }}
							style={[styles.image, { backgroundColor: colors.muted }]}
						/>
					) : (
						<View
							style={[
								styles.image,
								styles.imageMissing,
								{ backgroundColor: colors.surface },
							]}
						>
							<Icon name="image" size={32} color={colors.mutedForeground} />
						</View>
					)}
					<View style={styles.resultActions}>
						<View style={[styles.editPill, { backgroundColor: colors.surfaceRaised }]}>
							<Icon name="compose" size={15} color={colors.foreground} />
							<Text style={[styles.editPillText, { color: colors.foreground }]}>
								Редактировать
							</Text>
						</View>
						<Pressable
							accessibilityHint="Открывает системное меню отправки"
							accessibilityLabel="Поделиться изображением"
							accessibilityRole="button"
							disabled={!card.imageUrl}
							onPress={() => void share()}
							style={({ pressed }) => [
								styles.shareCircle,
								{ backgroundColor: colors.surfaceRaised },
								pressed && styles.pressed,
								!card.imageUrl && styles.disabled,
							]}
						>
							<Icon name="share" size={17} color={colors.foreground} />
						</Pressable>
					</View>
				</View>
			)}
		</View>
	);
}

const styles = StyleSheet.create({
	wrap: { maxWidth: 320 },
	skeleton: {
		alignItems: "center",
		borderRadius: 18,
		borderWidth: StyleSheet.hairlineWidth,
		gap: 9,
		height: 220,
		justifyContent: "center",
		width: 165,
	},
	thinking: { fontSize: 14, fontWeight: "600" },
	preview: {
		borderRadius: 18,
		borderWidth: StyleSheet.hairlineWidth,
		minHeight: 240,
		padding: 10,
		width: 300,
	},
	previewPill: {
		alignItems: "center",
		alignSelf: "flex-end",
		borderRadius: 999,
		paddingHorizontal: 10,
		paddingVertical: 5,
	},
	previewPillText: { fontSize: 12, fontWeight: "600" },
	thumbStrip: {
		flex: 1,
		flexDirection: "row",
		gap: 8,
		justifyContent: "center",
		paddingTop: 12,
	},
	thumb: {
		borderRadius: 10,
		borderWidth: StyleSheet.hairlineWidth,
		height: 74,
		width: 64,
	},
	thumbPlaceholder: { opacity: 0.7 },
	result: { width: 300 },
	image: {
		borderRadius: 18,
		height: 300,
		width: 300,
	},
	imageMissing: {
		alignItems: "center",
		justifyContent: "center",
	},
	resultActions: {
		alignItems: "center",
		flexDirection: "row",
		gap: 10,
		marginTop: 9,
		paddingHorizontal: 2,
	},
	editPill: {
		alignItems: "center",
		borderRadius: 999,
		flexDirection: "row",
		gap: 6,
		minHeight: 34,
		paddingHorizontal: 12,
	},
	editPillText: { fontSize: 13, fontWeight: "600" },
	shareCircle: {
		alignItems: "center",
		borderRadius: 17,
		height: 34,
		justifyContent: "center",
		width: 34,
	},
	pressed: { opacity: 0.6 },
	disabled: { opacity: 0.42 },
	invalid: {
		borderRadius: Radius.md,
		borderWidth: StyleSheet.hairlineWidth,
		maxWidth: 320,
		padding: 10,
	},
	invalidText: { fontSize: 13, lineHeight: 18 },
});

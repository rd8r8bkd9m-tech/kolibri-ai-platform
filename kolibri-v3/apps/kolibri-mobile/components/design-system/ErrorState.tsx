import { Pressable, StyleSheet, Text, View } from "react-native";

import { Icon } from "@/src/components/icons/Icon";
import { FontSize, FontWeight, Radius, Spacing } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";

export function ErrorState({
	message,
	retryId,
	onRetry,
}: {
	message: string;
	retryId?: string;
	onRetry?: () => void;
}) {
	const { colors } = useTheme();
	return (
		<View accessibilityRole="alert" style={styles.root}>
			<View style={[styles.icon, { backgroundColor: colors.destructiveSurface }]}>
				<Icon name="info" color={colors.destructive} size={28} />
			</View>
			<Text style={[styles.message, { color: colors.foreground }]}>
				{message}
			</Text>
			{retryId ? (
				<Text style={[styles.retryId, { color: colors.mutedForeground }]}>
					Код ошибки: {retryId}
				</Text>
			) : null}
			{onRetry ? (
				<Pressable
					accessibilityRole="button"
					onPress={onRetry}
					style={({ pressed }) => [
						styles.retry,
						{ backgroundColor: colors.surface },
						pressed && styles.pressed,
					]}
				>
					<Icon name="reload" color={colors.foreground} size={18} />
					<Text style={[styles.retryText, { color: colors.foreground }]}>
						Повторить
					</Text>
				</Pressable>
			) : null}
		</View>
	);
}

const styles = StyleSheet.create({
	root: {
		alignItems: "center",
		flex: 1,
		justifyContent: "center",
		paddingHorizontal: Spacing.xxxl,
	},
	icon: {
		alignItems: "center",
		borderRadius: Radius.badge,
		height: 64,
		justifyContent: "center",
		width: 64,
	},
	message: {
		fontSize: FontSize.body,
		fontWeight: FontWeight.semibold,
		marginTop: Spacing.lg,
		textAlign: "center",
	},
	retryId: {
		fontSize: FontSize.caption,
		marginTop: Spacing.sm,
		textAlign: "center",
	},
	retry: {
		alignItems: "center",
		borderRadius: Radius.control,
		flexDirection: "row",
		gap: Spacing.sm,
		marginTop: Spacing.xl,
		minHeight: 44,
		paddingHorizontal: Spacing.xl,
	},
	retryText: { fontSize: FontSize.medium, fontWeight: FontWeight.bold },
	pressed: { opacity: 0.62 },
});

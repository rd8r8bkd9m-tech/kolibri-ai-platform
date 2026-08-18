import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { Icon } from "@/src/components/icons/Icon";
import {
	FontSize,
	FontWeight,
	Radius,
	Spacing,
} from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import type { EstimateGenerationActivityWidget } from "@/src/product-chat/estimate-widget";

export function EstimateGenerationActivityCard({
	widget,
}: {
	widget: EstimateGenerationActivityWidget;
}) {
	const { colors } = useTheme();
	return (
		<View
			accessibilityLabel="Формирую смету"
			accessibilityLiveRegion="polite"
			style={[
				styles.card,
				{ backgroundColor: colors.surface, borderColor: colors.border },
			]}
		>
			<View style={[styles.icon, { backgroundColor: colors.infoBg }]}>
				<ActivityIndicator color={colors.send} size="small" />
			</View>
			<View style={styles.copy}>
				<Text style={[styles.title, { color: colors.foreground }]}>
					Формирую смету
				</Text>
				<Text style={[styles.meta, { color: colors.mutedForeground }]}>
					Проект {widget.projectId.slice(-8)} · версия {widget.projectCaseVersion}
				</Text>
			</View>
			<Icon name="document" color={colors.send} size={22} />
		</View>
	);
}

const styles = StyleSheet.create({
	card: {
		alignItems: "center",
		borderRadius: Radius.card,
		borderWidth: StyleSheet.hairlineWidth,
		flexDirection: "row",
		gap: Spacing.md,
		marginTop: Spacing.md,
		maxWidth: 360,
		padding: Spacing.lg,
	},
	icon: {
		alignItems: "center",
		borderRadius: Radius.md,
		height: 46,
		justifyContent: "center",
		width: 46,
	},
	copy: { flex: 1, minWidth: 0 },
	title: { fontSize: FontSize.body, fontWeight: FontWeight.bold },
	meta: { fontSize: FontSize.caption, marginTop: Spacing.xs },
});

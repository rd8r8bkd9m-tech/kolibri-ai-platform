import { useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { Icon } from "@/src/components/icons/Icon";
import {
	FontSize,
	FontWeight,
	Radius,
	Spacing,
} from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import type { EstimateEditorWidget } from "@/src/product-chat/estimate-widget";
import { fmtMoney } from "@/src/utils/format";

export function EstimateWidgetCard({
	widget,
}: {
	widget: EstimateEditorWidget;
}) {
	const router = useRouter();
	const { colors } = useTheme();
	const { estimate } = widget;
	return (
		<Pressable
			accessibilityHint="Открывает смету в мобильном редакторе"
			accessibilityLabel={`Смета ${estimate.estimateTitle}`}
			accessibilityRole="button"
			onPress={() =>
				router.push(
					`/estimate/${encodeURIComponent(widget.projectId)}?client=mobile`,
				)
			}
			style={({ pressed }) => [
				styles.card,
				{ backgroundColor: colors.surface, borderColor: colors.border },
				pressed && styles.pressed,
			]}
		>
			<View style={[styles.icon, { backgroundColor: colors.infoBg }]}>
				<Icon name="folder" color={colors.accentPurple} size={25} />
			</View>
			<View style={styles.copy}>
				<Text numberOfLines={1} style={[styles.title, { color: colors.foreground }]}>
					{estimate.estimateTitle}
				</Text>
				<Text style={[styles.meta, { color: colors.mutedForeground }]}>
					Смета · {estimate.rows.length} позиций · версия {estimate.version}
				</Text>
				<Text style={[styles.total, { color: colors.foreground }]}>
					{fmtMoney(Number(estimate.totals.total) || 0)}
				</Text>
			</View>
			<Icon name="chevron-right" color={colors.mutedForeground} size={22} />
		</Pressable>
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
	total: { fontSize: FontSize.text, fontWeight: FontWeight.bold, marginTop: Spacing.sm },
	pressed: { opacity: 0.62 },
});

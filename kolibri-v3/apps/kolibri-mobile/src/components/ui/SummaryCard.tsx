import { Platform, StyleSheet, Text, View } from "react-native";
import { useMemo } from "react";

import { FontSize, FontWeight, Spacing } from "@/constants/theme";
import { useDesignTokens } from "@/hooks/use-design-tokens";
import { fmtMoney } from "@/src/utils/format";

type SummaryCardProps = {
	sections: readonly { title: string; total: number }[];
	total: number;
};

export function SummaryCard({ sections, total }: SummaryCardProps) {
	const { colors, radii, typography, shadow } = useDesignTokens();
	const styles = useMemo(
		() => createStyles(colors, radii, typography, shadow),
		[colors, radii, typography, shadow],
	);
	return (
		<View style={styles.card}>
			{sections.map((section) => (
				<View key={section.title} style={styles.row}>
					<Text style={styles.sectionTitle}>{section.title}</Text>
					<Text style={styles.sectionTotal}>{fmtMoney(section.total)}</Text>
				</View>
			))}
			<View style={[styles.row, styles.totalRow]}>
				<Text style={styles.totalTitle}>Итого</Text>
				<Text style={styles.totalAmount}>{fmtMoney(total)}</Text>
			</View>
		</View>
	);
}

type SummaryTokens = ReturnType<typeof useDesignTokens>;

const createStyles = (
	colors: SummaryTokens["colors"],
	radii: SummaryTokens["radii"],
	typography: SummaryTokens["typography"],
	shadow: SummaryTokens["shadow"],
) =>
	StyleSheet.create({
		card: {
			backgroundColor: colors.surface,
			borderRadius: radii.card,
			padding: Spacing.xl,
			...Platform.select({
				web: { boxShadow: "0 24px 70px rgba(0, 0, 0, 0.42)" },
				ios: {
					shadowColor: shadow.shadowColor,
					shadowOffset: shadow.shadowOffset,
					shadowOpacity: shadow.shadowOpacity,
					shadowRadius: shadow.shadowRadius,
				},
				default: { elevation: shadow.elevation },
			}),
		},
		row: {
			alignItems: "center",
			flexDirection: "row",
			justifyContent: "space-between",
			paddingVertical: Spacing.sm,
		},
		sectionTitle: {
			color: colors.textPrimary,
			fontSize: FontSize.body,
			fontWeight: FontWeight.semibold,
		},
		sectionTotal: {
			color: colors.textTertiary,
			fontSize: FontSize.body,
			fontWeight: FontWeight.semibold,
		},
		totalRow: {
			borderTopColor: colors.divider,
			borderTopWidth: StyleSheet.hairlineWidth,
			marginTop: Spacing.sm,
			paddingTop: Spacing.lg,
		},
		totalTitle: { ...typography.listItem, color: colors.textPrimary },
		totalAmount: { ...typography.amountXL, color: colors.textPrimary },
	});

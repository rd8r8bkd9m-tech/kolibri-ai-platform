import { StyleSheet, Text, View } from "react-native";
import { useMemo } from "react";

import { FontSize, FontWeight, Spacing } from "@/constants/theme";
import { useDesignTokens } from "@/hooks/use-design-tokens";
import { fmtMoney } from "@/src/utils/format";

export function TotalPreview({ total }: { total: number }) {
	const { colors, radii } = useDesignTokens();
	const styles = useMemo(() => createStyles(colors, radii), [colors, radii]);
	return (
		<View
			accessibilityLabel={`Итого ${fmtMoney(total)}`}
			style={styles.box}
		>
			<Text style={styles.label}>Итого</Text>
			<Text style={styles.amount}>{fmtMoney(total)}</Text>
		</View>
	);
}

type TotalPreviewColors = ReturnType<typeof useDesignTokens>["colors"];
type TotalPreviewRadii = ReturnType<typeof useDesignTokens>["radii"];

const createStyles = (colors: TotalPreviewColors, radii: TotalPreviewRadii) =>
	StyleSheet.create({
		box: {
			alignItems: "center",
			backgroundColor: colors.draftBg,
			borderRadius: radii.input,
			flexDirection: "row",
			justifyContent: "space-between",
			minHeight: 52,
			paddingHorizontal: Spacing.lg,
		},
		label: {
			color: colors.textSecondary,
			fontSize: FontSize.medium,
			fontWeight: FontWeight.semibold,
		},
		amount: {
			color: colors.accent,
			fontSize: FontSize.text,
			fontWeight: FontWeight.bold,
		},
	});

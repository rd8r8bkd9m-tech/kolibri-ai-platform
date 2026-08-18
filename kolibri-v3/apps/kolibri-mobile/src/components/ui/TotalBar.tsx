import { Platform, StyleSheet, Text, View } from "react-native";
import { useMemo } from "react";

import { PillButton } from "@/src/components/ui/PillButton";
import { Spacing } from "@/constants/theme";
import { useDesignTokens } from "@/hooks/use-design-tokens";
import { fmtMoney } from "@/src/utils/format";

type TotalBarProps = {
	total: number;
	onAdd: () => void;
};

export function TotalBar({ total, onAdd }: TotalBarProps) {
	const { colors, radii, shadow, typography } = useDesignTokens();
	const styles = useMemo(
		() => createStyles(colors, radii, shadow, typography),
		[colors, radii, shadow, typography],
	);
	return (
		<View
			style={[
				styles.bar,
				{ marginBottom: Spacing.md },
			]}
		>
			<View style={styles.total}>
				<Text style={styles.label}>Итого</Text>
				<Text style={styles.amount}>{fmtMoney(total)}</Text>
			</View>
			<PillButton
				filled
				icon="plus"
				onPress={onAdd}
				title="Добавить позицию"
			/>
		</View>
	);
}

type TotalBarTokens = ReturnType<typeof useDesignTokens>;

const createStyles = (
	colors: TotalBarTokens["colors"],
	radii: TotalBarTokens["radii"],
	shadow: TotalBarTokens["shadow"],
	typography: TotalBarTokens["typography"],
) =>
	StyleSheet.create({
		bar: {
			alignItems: "center",
			backgroundColor: colors.surface,
			borderRadius: radii.card,
			flexDirection: "row",
			justifyContent: "space-between",
			marginHorizontal: Spacing.lg,
			padding: Spacing.lg,
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
		total: { marginRight: Spacing.md },
		label: { ...typography.label, color: colors.textTertiary },
		amount: { ...typography.amountL, color: colors.textPrimary },
	});

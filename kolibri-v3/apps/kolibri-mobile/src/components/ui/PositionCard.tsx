import { Pressable, StyleSheet, Text, View } from "react-native";
import { useMemo } from "react";

import { FontSize, FontWeight, LineHeight, Spacing } from "@/constants/theme";
import { useDesignTokens } from "@/hooks/use-design-tokens";
import { fmtMoney, fmtQty, lineTotal } from "@/src/utils/format";

type PositionCardProps = {
	name: string;
	qty: number;
	unit: string;
	price: number;
	onPress?: () => void;
	onLongPress?: () => void;
	accessibilityLabel?: string;
};

export function PositionCard({
	name,
	qty,
	unit,
	price,
	onPress,
	onLongPress,
	accessibilityLabel,
}: PositionCardProps) {
	const { colors, radii } = useDesignTokens();
	const styles = useMemo(() => createStyles(colors, radii), [colors, radii]);
	const total = lineTotal(qty, price);
	const label = accessibilityLabel ?? `${name}, ${fmtMoney(total)}`;
	return (
		<Pressable
			accessibilityLabel={label}
			accessibilityRole="button"
			onLongPress={onLongPress}
			onPress={onPress}
			style={({ pressed }) => [styles.card, pressed && styles.pressed]}
		>
			<View style={styles.row}>
				<Text numberOfLines={2} style={styles.name}>
					{name}
				</Text>
				<Text style={styles.amount}>{fmtMoney(total)}</Text>
			</View>
			<Text style={styles.meta}>
				{fmtQty(qty)} {unit} × {fmtMoney(price)}
			</Text>
		</Pressable>
	);
}

type PositionCardColors = ReturnType<typeof useDesignTokens>["colors"];
type PositionCardRadii = ReturnType<typeof useDesignTokens>["radii"];

const createStyles = (colors: PositionCardColors, radii: PositionCardRadii) =>
	StyleSheet.create({
		card: {
			backgroundColor: colors.surface,
			borderRadius: radii.positionCard,
			padding: Spacing.lg,
		},
		row: {
			alignItems: "flex-start",
			flexDirection: "row",
			gap: Spacing.md,
		},
		name: {
			color: colors.textPrimary,
			flex: 1,
			fontSize: FontSize.body,
			fontWeight: FontWeight.semibold,
			lineHeight: LineHeight.base,
		},
		amount: {
			color: colors.textPrimary,
			fontSize: FontSize.text,
			fontWeight: FontWeight.bold,
		},
		meta: {
			color: colors.textTertiary,
			fontSize: FontSize.small,
			marginTop: Spacing.xs,
		},
		pressed: { opacity: 0.8, transform: [{ scale: 0.98 }] },
	});

import { Pressable, ScrollView, StyleSheet, Text } from "react-native";
import { useMemo } from "react";

import { FontSize, FontWeight, Spacing } from "@/constants/theme";
import { useDesignTokens } from "@/hooks/use-design-tokens";

type ChipsRowProps = {
	options: readonly string[];
	selected: string;
	onSelect: (value: string) => void;
};

export function ChipsRow({ options, selected, onSelect }: ChipsRowProps) {
	const { colors, radii } = useDesignTokens();
	const styles = useMemo(() => createStyles(colors, radii), [colors, radii]);
	return (
		<ScrollView
			contentContainerStyle={styles.row}
			horizontal
			showsHorizontalScrollIndicator={false}
		>
			{options.map((option) => {
				const active = option === selected;
				return (
					<Pressable
						accessibilityRole="button"
						accessibilityState={{ selected: active }}
						key={option}
						onPress={() => onSelect(option)}
						style={({ pressed }) => [
							styles.chip,
							active && styles.chipActive,
							pressed && styles.pressed,
						]}
					>
						<Text style={[styles.label, active && styles.labelActive]}>
							{option}
						</Text>
					</Pressable>
				);
			})}
		</ScrollView>
	);
}

type ChipsRowColors = ReturnType<typeof useDesignTokens>["colors"];
type ChipsRowRadii = ReturnType<typeof useDesignTokens>["radii"];

const createStyles = (colors: ChipsRowColors, radii: ChipsRowRadii) =>
	StyleSheet.create({
		row: { gap: Spacing.sm, paddingVertical: Spacing.xs },
		chip: {
			alignItems: "center",
			backgroundColor: colors.surface,
			borderColor: colors.borderLight,
			borderRadius: radii.full,
			borderWidth: 1,
			justifyContent: "center",
			minHeight: 40,
			paddingHorizontal: Spacing.lg,
		},
		chipActive: {
			backgroundColor: colors.textPrimary,
			borderColor: colors.textPrimary,
		},
		label: {
			color: colors.textPrimary,
			fontSize: FontSize.medium,
			fontWeight: FontWeight.semibold,
		},
		labelActive: { color: colors.surface },
		pressed: { opacity: 0.8 },
	});

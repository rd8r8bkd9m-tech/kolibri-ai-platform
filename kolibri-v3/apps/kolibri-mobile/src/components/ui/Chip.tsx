import {
	StyleSheet,
	Text,
	View,
	type StyleProp,
	type ViewStyle,
} from "react-native";
import { useMemo } from "react";

import type { IconName } from "@/components/ui/icon-mappings";
import { Icon } from "@/src/components/icons/Icon";
import { FontSize, FontWeight, Spacing } from "@/constants/theme";
import { useDesignTokens } from "@/hooks/use-design-tokens";

export function Chip({
	icon,
	label,
	iconColor,
	style,
}: {
	icon: IconName;
	label: string;
	iconColor: string;
	style?: StyleProp<ViewStyle>;
}) {
	const { colors, radii } = useDesignTokens();
	const styles = useMemo(() => createStyles(colors, radii), [colors, radii]);
	return (
		<View accessibilityLabel={label} style={[styles.chip, style]}>
			<Icon name={icon} size={24} color={iconColor} />
			<Text style={styles.label}>{label}</Text>
		</View>
	);
}

type ChipColors = ReturnType<typeof useDesignTokens>["colors"];
type ChipRadii = ReturnType<typeof useDesignTokens>["radii"];

const createStyles = (colors: ChipColors, radii: ChipRadii) =>
	StyleSheet.create({
		chip: {
			alignItems: "center",
			backgroundColor: colors.surface,
			borderColor: colors.borderLight,
			borderRadius: radii.full,
			borderWidth: 1,
			flexDirection: "row",
			gap: Spacing.sm,
			height: 56,
			paddingHorizontal: Spacing.lg,
		},
		label: {
			color: colors.textPrimary,
			fontSize: FontSize.text,
			fontWeight: FontWeight.semibold,
		},
	});

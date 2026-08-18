import {
	Platform,
	Pressable,
	StyleSheet,
	Text,
	type StyleProp,
	type ViewStyle,
} from "react-native";
import { useMemo } from "react";

import type { IconName } from "@/components/ui/icon-mappings";
import { Icon } from "@/src/components/icons/Icon";
import { Spacing } from "@/constants/theme";
import { useDesignTokens } from "@/hooks/use-design-tokens";

type PillButtonProps = {
	title: string;
	icon?: IconName;
	iconColor?: string;
	textColor?: string;
	filled?: boolean;
	underline?: boolean;
	disabled?: boolean;
	onPress?: () => void;
	onLongPress?: () => void;
	accessibilityLabel?: string;
	testID?: string;
	style?: StyleProp<ViewStyle>;
};

export function PillButton({
	title,
	icon,
	iconColor,
	textColor,
	filled = false,
	underline = false,
	disabled = false,
	onPress,
	onLongPress,
	accessibilityLabel,
	testID,
	style,
}: PillButtonProps) {
	const { colors, radii, shadow, typography } = useDesignTokens();
	const styles = useMemo(
		() => createStyles(colors, radii, shadow),
		[colors, radii, shadow],
	);
	return (
		<Pressable
			accessibilityRole="button"
			accessibilityLabel={accessibilityLabel ?? title}
			accessibilityState={{ disabled }}
			disabled={disabled}
			onLongPress={onLongPress}
			onPress={onPress}
			testID={testID}
			style={({ pressed }) => [
				styles.root,
				filled && styles.filled,
				disabled && styles.disabled,
				pressed && !disabled && styles.pressed,
				style,
			]}
		>
			{icon ? (
				<Icon
					name={icon}
					size={24}
					color={disabled ? colors.textTertiary : iconColor ?? (filled ? colors.surface : colors.textPrimary)}
				/>
			) : null}
			<Text
				style={[
					typography.pillLabel,
					{ color: disabled ? colors.textTertiary : textColor ?? (filled ? colors.surface : colors.textPrimary) },
					underline && styles.underline,
				]}
			>
				{title}
			</Text>
		</Pressable>
	);
}

type PillButtonColors = ReturnType<typeof useDesignTokens>["colors"];
type PillButtonRadii = ReturnType<typeof useDesignTokens>["radii"];
type PillButtonShadow = ReturnType<typeof useDesignTokens>["shadow"];

const createStyles = (
	colors: PillButtonColors,
	radii: PillButtonRadii,
	shadow: PillButtonShadow,
) =>
	StyleSheet.create({
		root: {
			alignItems: "center",
			borderColor: colors.borderDark,
			borderRadius: radii.full,
			borderWidth: 1,
			flexDirection: "row",
			gap: Spacing.sm,
			height: 52,
			justifyContent: "center",
			paddingHorizontal: Spacing.xxl,
		},
		filled: {
			backgroundColor: colors.textPrimary,
			borderWidth: 0,
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
		underline: { textDecorationLine: "underline" },
		disabled: {
			backgroundColor: colors.disabled,
			borderColor: colors.disabled,
		},
		pressed: { opacity: 0.8, transform: [{ scale: 0.97 }] },
	});

import type { ReactNode } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { Icon } from "@/src/components/icons/Icon";
import type { IconName } from "@/components/ui/icon-mappings";
import {
	LineHeight,
	Radius,
	Spacing,
	typography,
} from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";

type SettingsRowProps = {
	accessibilityHint?: string;
	destructive?: boolean;
	disabled?: boolean;
	icon: IconName;
	last?: boolean;
	onPress?: () => void;
	title: string;
	trailing?: ReactNode;
	value?: string;
};

export function SettingsRow({
	accessibilityHint,
	destructive = false,
	disabled = false,
	icon,
	last = false,
	onPress,
	title,
	trailing,
	value,
}: SettingsRowProps) {
	const { colors } = useTheme();
	const contentColor = destructive ? colors.destructive : colors.foreground;
	return (
		<Pressable
			accessibilityHint={accessibilityHint}
			accessibilityLabel={value ? `${title}, ${value}` : title}
			accessibilityRole={onPress ? "button" : "text"}
			accessibilityState={{ disabled }}
			disabled={disabled || !onPress}
			onPress={() => {
				haptics.selection();
				onPress?.();
			}}
			style={({ pressed }) => [
				styles.row,
				!last && { borderBottomColor: colors.border, borderBottomWidth: StyleSheet.hairlineWidth },
				pressed && styles.pressed,
				disabled && styles.disabled,
			]}
		>
			<View
				style={[
					styles.icon,
					{ backgroundColor: destructive ? colors.destructiveSurface : colors.muted },
				]}
			>
				<Icon name={icon} size={18} color={contentColor} />
			</View>
			<Text
				numberOfLines={1}
				style={[typography.settingsRow, styles.title, { color: contentColor }]}
			>
				{title}
			</Text>
			<View style={styles.trailing}>
				{value ? (
					<Text
						numberOfLines={1}
						style={[
							typography.settingsValue,
							styles.value,
							{ color: colors.mutedForeground },
						]}
					>
						{value}
					</Text>
				) : null}
				{trailing}
				{onPress && !trailing ? (
					<Icon name="chevron-right" size={18} color={colors.mutedForeground} />
				) : null}
			</View>
		</Pressable>
	);
}

const styles = StyleSheet.create({
	row: {
		alignItems: "center",
		flexDirection: "row",
		marginLeft: Spacing.lg,
		minHeight: 56,
		paddingRight: Spacing.lg,
	},
	icon: {
		alignItems: "center",
		borderRadius: Radius.sm,
		height: 30,
		justifyContent: "center",
		marginRight: Spacing.md,
		width: 30,
	},
	title: { flexShrink: 0, lineHeight: LineHeight.base },
	trailing: {
		alignItems: "center",
		flex: 1,
		flexDirection: "row",
		gap: Spacing.sm,
		justifyContent: "flex-end",
		marginLeft: Spacing.md,
		minWidth: 0,
	},
	value: { flexShrink: 1, lineHeight: LineHeight.small },
	pressed: { opacity: 0.62 },
	disabled: { opacity: 0.46 },
});

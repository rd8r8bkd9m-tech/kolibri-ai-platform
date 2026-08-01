import type { ReactNode } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { Icon } from "@/components/ui/icon";
import type { IconName } from "@/components/ui/icon-mappings";
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
			<Text numberOfLines={1} style={[styles.title, { color: contentColor }]}>
				{title}
			</Text>
			<View style={styles.trailing}>
				{value ? (
					<Text
						numberOfLines={1}
						style={[styles.value, { color: colors.mutedForeground }]}
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
		marginLeft: 14,
		minHeight: 56,
		paddingRight: 14,
	},
	icon: {
		alignItems: "center",
		borderRadius: 8,
		height: 30,
		justifyContent: "center",
		marginRight: 12,
		width: 30,
	},
	title: { flexShrink: 0, fontSize: 16, fontWeight: "500", lineHeight: 21 },
	trailing: {
		alignItems: "center",
		flex: 1,
		flexDirection: "row",
		gap: 7,
		justifyContent: "flex-end",
		marginLeft: 12,
		minWidth: 0,
	},
	value: { flexShrink: 1, fontSize: 14, lineHeight: 19 },
	pressed: { opacity: 0.62 },
	disabled: { opacity: 0.46 },
});

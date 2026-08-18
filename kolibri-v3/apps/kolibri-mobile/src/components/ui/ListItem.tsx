import {
	Pressable,
	StyleSheet,
	Text,
	View,
	type StyleProp,
	type ViewStyle,
} from "react-native";
import { useMemo } from "react";

import type { IconName } from "@/components/ui/icon-mappings";
import { Icon } from "@/src/components/icons/Icon";
import { FontWeight, Spacing } from "@/constants/theme";
import { useDesignTokens } from "@/hooks/use-design-tokens";

type ListItemProps = {
	title: string;
	icon: IconName;
	iconColor?: string;
	subtitle?: string;
	bold?: boolean;
	onPress?: () => void;
	onLongPress?: () => void;
	testID?: string;
	style?: StyleProp<ViewStyle>;
};

export function ListItem({
	title,
	icon,
	iconColor,
	subtitle,
	bold = false,
	onPress,
	onLongPress,
	testID,
	style,
}: ListItemProps) {
	const { colors, typography } = useDesignTokens();
	const styles = useMemo(() => createStyles(), []);
	const resolvedIconColor = iconColor ?? colors.textPrimary;
	return (
		<Pressable
			accessibilityRole="button"
			accessibilityLabel={subtitle ? `${title}, ${subtitle}` : title}
			delayLongPress={250}
			onLongPress={onLongPress}
			onPress={onPress}
			testID={testID}
			style={({ pressed }) => [styles.row, pressed && styles.pressed, style]}
		>
			<Icon name={icon} size={24} color={resolvedIconColor} />
			<View style={styles.copy}>
				<Text
					numberOfLines={1}
					style={[
						typography.listItem,
						{
							color: colors.textPrimary,
							fontWeight: bold
								? FontWeight.bold
								: FontWeight.semibold,
						},
					]}
				>
					{title}
				</Text>
				{subtitle ? (
					<Text
						numberOfLines={1}
						style={[typography.body, { color: colors.textTertiary }]}
					>
						{subtitle}
					</Text>
				) : null}
			</View>
		</Pressable>
	);
}

const createStyles = () =>
	StyleSheet.create({
		row: {
			alignItems: "center",
			flexDirection: "row",
			gap: Spacing.lg,
			minHeight: 56,
			paddingHorizontal: Spacing.xs,
		},
		copy: { flex: 1, minWidth: 0 },
		pressed: { opacity: 0.8, transform: [{ scale: 0.97 }] },
	});

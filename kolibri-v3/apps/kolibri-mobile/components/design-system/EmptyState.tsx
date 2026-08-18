import { StyleSheet, Text, View } from "react-native";

import { Icon } from "@/src/components/icons/Icon";
import type { IconName } from "@/components/ui/icon-mappings";
import { FontSize, FontWeight, Radius, Spacing } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";

export function EmptyState({
	icon,
	title,
	body,
	note,
}: {
	icon: IconName;
	title: string;
	body: string;
	note?: string;
}) {
	const { colors } = useTheme();
	return (
		<View style={styles.root}>
			<View style={[styles.icon, { backgroundColor: colors.surface }]}>
				<Icon name={icon} color={colors.send} size={30} />
			</View>
			<Text style={[styles.title, { color: colors.foreground }]}>{title}</Text>
			<Text style={[styles.body, { color: colors.mutedForeground }]}>{body}</Text>
			{note ? (
				<Text style={[styles.note, { color: colors.mutedForeground }]}>
					{note}
				</Text>
			) : null}
		</View>
	);
}

const styles = StyleSheet.create({
	root: {
		alignItems: "center",
		flex: 1,
		justifyContent: "center",
		paddingHorizontal: Spacing.xxxl,
		paddingBottom: Spacing.xxxl * 2 + Spacing.sm,
	},
	icon: {
		alignItems: "center",
		borderRadius: Radius.badge,
		height: 68,
		justifyContent: "center",
		width: 68,
	},
	title: {
		fontSize: FontSize.h3,
		fontWeight: FontWeight.bold,
		marginTop: Spacing.xl,
		textAlign: "center",
	},
	body: {
		fontSize: FontSize.medium,
		lineHeight: 21,
		marginTop: Spacing.md,
		textAlign: "center",
	},
	note: {
		fontSize: FontSize.caption,
		lineHeight: 17,
		marginTop: Spacing.md,
		textAlign: "center",
	},
});

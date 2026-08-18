import { StyleSheet, Text, View } from "react-native";

import {
	FontSize,
	FontWeight,
	LetterSpacing,
	LineHeight,
	Radius,
	Spacing,
	typography,
} from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";

export function profileInitials(name: string) {
	return (
		name
			.split(/\s+/)
			.map((part) => part.trim())
			.filter(Boolean)
			.slice(0, 2)
			.map((part) => part[0]?.toLocaleUpperCase("ru-RU") ?? "")
			.join("") || "К"
	);
}

type IdentitySummaryProps = {
	email: string;
	isOwner: boolean;
	name: string;
};

export function IdentitySummary({ email, isOwner, name }: IdentitySummaryProps) {
	const { colors } = useTheme();
	return (
		<View style={styles.root}>
			<View style={[styles.avatar, { backgroundColor: colors.foreground }]}>
				<Text style={[styles.avatarText, { color: colors.primaryForeground }]}>
					{profileInitials(name)}
				</Text>
			</View>
			<View style={styles.copy}>
				<Text
					numberOfLines={1}
					style={[
						typography.identityName,
						styles.name,
						{ color: colors.foreground },
					]}
				>
					{name}
				</Text>
				<Text
					numberOfLines={1}
					selectable
					style={[
						typography.identityEmail,
						styles.email,
						{ color: colors.mutedForeground },
					]}
				>
					{email}
				</Text>
				{isOwner ? (
					<View style={[styles.badge, { backgroundColor: colors.muted }]}>
						<Text style={[styles.badgeText, { color: colors.foreground }]}>
							Владелец платформы
						</Text>
					</View>
				) : null}
			</View>
		</View>
	);
}

const styles = StyleSheet.create({
	root: {
		alignItems: "center",
		flexDirection: "row",
		minHeight: 92,
		paddingHorizontal: Spacing.xs,
	},
	avatar: {
		alignItems: "center",
		borderRadius: Radius.badge,
		height: 64,
		justifyContent: "center",
		width: 64,
	},
	avatarText: {
		fontSize: FontSize.avatar,
		fontWeight: FontWeight.bold,
		letterSpacing: LetterSpacing.base,
	},
	copy: { flex: 1, marginLeft: Spacing.lg, minWidth: 0 },
	name: { letterSpacing: LetterSpacing.medium, lineHeight: LineHeight.text },
	email: { lineHeight: LineHeight.small, marginTop: Spacing.xs },
	badge: {
		alignSelf: "flex-start",
		borderRadius: Radius.circle,
		marginTop: Spacing.sm,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.xs,
	},
	badgeText: {
		fontSize: FontSize.caption2,
		fontWeight: FontWeight.bold,
		lineHeight: LineHeight.caption2,
	},
});

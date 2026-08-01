import { StyleSheet, Text, View } from "react-native";

import { Radius } from "@/constants/theme";
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
				<Text numberOfLines={1} style={[styles.name, { color: colors.foreground }]}>
					{name}
				</Text>
				<Text
					numberOfLines={1}
					selectable
					style={[styles.email, { color: colors.mutedForeground }]}
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
		paddingHorizontal: 4,
	},
	avatar: {
		alignItems: "center",
		borderRadius: 32,
		height: 64,
		justifyContent: "center",
		width: 64,
	},
	avatarText: { fontSize: 23, fontWeight: "700", letterSpacing: -0.3 },
	copy: { flex: 1, marginLeft: 15, minWidth: 0 },
	name: { fontSize: 20, fontWeight: "700", letterSpacing: -0.35, lineHeight: 25 },
	email: { fontSize: 14, lineHeight: 19, marginTop: 1 },
	badge: {
		alignSelf: "flex-start",
		borderRadius: Radius.circle,
		marginTop: 7,
		paddingHorizontal: 9,
		paddingVertical: 4,
	},
	badgeText: { fontSize: 11, fontWeight: "700", lineHeight: 14 },
});

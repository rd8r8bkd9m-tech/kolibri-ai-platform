import type { PropsWithChildren, ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";

import { Radius } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";

type SettingsGroupProps = PropsWithChildren<{
	footer?: ReactNode;
	title?: string;
}>;

export function SettingsGroup({ children, footer, title }: SettingsGroupProps) {
	const { colors } = useTheme();
	return (
		<View style={styles.root}>
			{title ? (
				<Text style={[styles.title, { color: colors.mutedForeground }]}>
					{title}
				</Text>
			) : null}
			<View
				style={[
					styles.surface,
					{ backgroundColor: colors.surfaceRaised },
				]}
			>
				{children}
			</View>
			{footer ? <View style={styles.footer}>{footer}</View> : null}
		</View>
	);
}

const styles = StyleSheet.create({
	root: { gap: 7 },
	title: {
		fontSize: 13,
		fontWeight: "600",
		letterSpacing: -0.05,
		lineHeight: 18,
		paddingHorizontal: 4,
	},
	surface: {
		borderRadius: Radius.card,
		overflow: "hidden",
	},
	footer: { paddingHorizontal: 4 },
});

import type { PropsWithChildren, ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";

import {
	LineHeight,
	Radius,
	Spacing,
	typography,
} from "@/constants/theme";
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
				<Text
					style={[
						typography.settingsLabel,
						styles.title,
						{ color: colors.mutedForeground },
					]}
				>
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
	root: { gap: Spacing.sm },
	title: {
		lineHeight: LineHeight.compact,
		paddingHorizontal: Spacing.xs,
	},
	surface: {
		borderRadius: Radius.card,
		overflow: "hidden",
	},
	footer: { paddingHorizontal: Spacing.xs },
});

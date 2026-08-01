import type { ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";

import { CircleButton } from "@/components/shell/circle-button";
import { Icon } from "@/components/ui/icon";
import { Layout } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";

type NativeScreenHeaderProps = {
	onBack: () => void;
	title: string;
	trailing?: ReactNode;
};

export function NativeScreenHeader({
	onBack,
	title,
	trailing,
}: NativeScreenHeaderProps) {
	const { colors } = useTheme();
	return (
		<View style={styles.root}>
			<CircleButton
				accessibilityLabel="Назад к чату"
				accessibilityRole="button"
				onPress={() => {
					haptics.selection();
					onBack();
				}}
			>
				<Icon
					name="chevron-left"
					size={25}
					color={colors.foreground}
				/>
			</CircleButton>
			<Text
				accessibilityRole="header"
				numberOfLines={1}
				style={[styles.title, { color: colors.foreground }]}
			>
				{title}
			</Text>
			<View style={styles.trailing}>{trailing}</View>
		</View>
	);
}

const styles = StyleSheet.create({
	root: {
		alignItems: "center",
		flexDirection: "row",
		height: 68,
		justifyContent: "space-between",
		paddingHorizontal: Layout.edgeInset,
	},
	title: {
		fontSize: 17,
		fontWeight: "700",
		left: Layout.edgeInset + Layout.headerControl,
		letterSpacing: -0.2,
		lineHeight: 22,
		position: "absolute",
		right: Layout.edgeInset + Layout.headerControl,
		textAlign: "center",
	},
	trailing: {
		alignItems: "center",
		height: Layout.headerControl,
		justifyContent: "center",
		width: Layout.headerControl,
	},
});

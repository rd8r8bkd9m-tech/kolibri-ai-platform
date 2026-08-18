import type { ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";

import { CircleButton } from "@/components/shell/circle-button";
import { Icon } from "@/src/components/icons/Icon";
import {
	FontSize,
	FontWeight,
	Layout,
	LetterSpacing,
	LineHeight,
	Spacing,
} from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";

type NativeScreenHeaderProps = {
	onBack: () => void;
	subtitle?: string;
	title: string;
	trailing?: ReactNode;
};

export function NativeScreenHeader({
	onBack,
	subtitle,
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
			<View style={styles.titleWrap}>
				<Text
					accessibilityRole="header"
					numberOfLines={1}
					style={[styles.title, { color: colors.foreground }]}
				>
					{title}
				</Text>
				{subtitle ? (
					<Text
						numberOfLines={1}
						style={[styles.subtitle, { color: colors.mutedForeground }]}
					>
						{subtitle}
					</Text>
				) : null}
			</View>
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
		fontSize: FontSize.text,
		fontWeight: FontWeight.bold,
		left: Layout.edgeInset + Layout.headerControl,
		letterSpacing: LetterSpacing.relaxed,
		lineHeight: LineHeight.body,
		position: "absolute",
		right: Layout.edgeInset + Layout.headerControl,
		textAlign: "center",
	},
	titleWrap: {
		alignItems: "center",
		left: Layout.edgeInset + Layout.headerControl,
		position: "absolute",
		right: Layout.edgeInset + Layout.headerControl,
	},
	subtitle: {
		fontSize: FontSize.caption,
		lineHeight: LineHeight.caption,
		marginTop: Spacing.xs,
		textAlign: "center",
	},
	trailing: {
		alignItems: "center",
		height: Layout.headerControl,
		justifyContent: "center",
		width: Layout.headerControl,
	},
});

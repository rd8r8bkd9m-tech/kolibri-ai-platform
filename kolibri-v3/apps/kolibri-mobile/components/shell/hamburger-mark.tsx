import { StyleSheet, View } from "react-native";

import { Radius, Spacing } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";

export function HamburgerMark() {
	const { colors } = useTheme();
	return (
		<View
			accessibilityElementsHidden
			importantForAccessibility="no"
			style={styles.mark}
		>
			<View style={[styles.line, { backgroundColor: colors.foreground }]} />
			<View
				style={[
					styles.line,
					styles.lineShort,
					{ backgroundColor: colors.foreground },
				]}
			/>
		</View>
	);
}

const styles = StyleSheet.create({
	mark: { gap: Spacing.sm },
	line: { borderRadius: Radius.xxs, height: 3, width: 26 },
	lineShort: { width: 17 },
});

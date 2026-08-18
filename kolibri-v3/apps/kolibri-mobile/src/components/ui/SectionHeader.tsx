import { StyleSheet, Text } from "react-native";
import { useMemo } from "react";

import { Spacing } from "@/constants/theme";
import { useDesignTokens } from "@/hooks/use-design-tokens";

export function SectionHeader({ title }: { title: string }) {
	const { colors, typography } = useDesignTokens();
	const styles = useMemo(() => createStyles(colors), [colors]);
	return (
		<Text accessibilityRole="header" style={[typography.hSection, styles.title]}>
			{title}
		</Text>
	);
}

type SectionHeaderColors = ReturnType<typeof useDesignTokens>["colors"];

const createStyles = (colors: SectionHeaderColors) =>
	StyleSheet.create({
		title: { color: colors.textPrimary, marginTop: Spacing.xxxl },
	});

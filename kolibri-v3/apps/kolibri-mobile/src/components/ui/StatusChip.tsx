import { StyleSheet, Text, View } from "react-native";
import { useMemo } from "react";

import { FontSize, FontWeight, Spacing } from "@/constants/theme";
import { useDesignTokens } from "@/hooks/use-design-tokens";

export type EstimateStatus = "draft" | "sent" | "approved";

export function StatusChip({
	status,
	label,
}: {
	status: EstimateStatus;
	label?: string;
}) {
	const { colors, radii } = useDesignTokens();
	const styles = useMemo(() => createStyles(radii), [radii]);
	const STATUS: Record<
		EstimateStatus,
		{ background: string; foreground: string; label: string }
	> = {
		draft: {
			background: colors.draftBg,
			foreground: colors.textSecondary,
			label: "Черновик",
		},
		sent: {
			background: colors.infoBg,
			foreground: colors.accent,
			label: "Отправлена",
		},
		approved: {
			background: colors.successBg,
			foreground: colors.success,
			label: "Утверждена",
		},
	};
	const value = STATUS[status];
	return (
		<View
			accessibilityLabel={label ?? value.label}
			style={[styles.chip, { backgroundColor: value.background }]}
		>
			<Text style={[styles.label, { color: value.foreground }]}>
				{label ?? value.label}
			</Text>
		</View>
	);
}

type StatusChipRadii = ReturnType<typeof useDesignTokens>["radii"];

const createStyles = (radii: StatusChipRadii) =>
	StyleSheet.create({
		chip: {
			alignItems: "center",
			borderRadius: radii.full,
			height: 24,
			justifyContent: "center",
			paddingHorizontal: Spacing.md,
		},
		label: { fontSize: FontSize.caption, fontWeight: FontWeight.semibold },
	});

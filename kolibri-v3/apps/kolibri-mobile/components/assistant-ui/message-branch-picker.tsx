import { BranchPickerPrimitive, useAuiState } from "@assistant-ui/react-native";
import { StyleSheet, Text, View } from "react-native";

import { Icon } from "@/src/components/icons/Icon";
import { FontSize, Spacing } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";

export function MessageBranchPicker({
	align = "flex-start",
}: {
	align?: "flex-start" | "flex-end";
}) {
	const { colors } = useTheme();
	const number = useAuiState((state) => state.message.branchNumber);
	const count = useAuiState((state) => state.message.branchCount);
	if (count <= 1) return null;

	return (
		<View style={[styles.root, { justifyContent: align }]}>
			<BranchPickerPrimitive.Previous
				accessibilityLabel="Предыдущая версия"
				hitSlop={4}
				style={[styles.button, { opacity: number <= 1 ? 0.35 : 1 }]}
			>
				<Icon name="chevron-left" size={16} color={colors.mutedForeground} />
			</BranchPickerPrimitive.Previous>
			<Text style={[styles.label, { color: colors.mutedForeground }]}>
				<BranchPickerPrimitive.Number /> / <BranchPickerPrimitive.Count />
			</Text>
			<BranchPickerPrimitive.Next
				accessibilityLabel="Следующая версия"
				hitSlop={4}
				style={[styles.button, { opacity: number >= count ? 0.35 : 1 }]}
			>
				<Icon name="chevron-right" size={16} color={colors.mutedForeground} />
			</BranchPickerPrimitive.Next>
		</View>
	);
}

const styles = StyleSheet.create({
	root: { alignItems: "center", flexDirection: "row", gap: Spacing.xs },
	button: { padding: Spacing.xs },
	label: { fontSize: FontSize.caption, fontVariant: ["tabular-nums"] },
});

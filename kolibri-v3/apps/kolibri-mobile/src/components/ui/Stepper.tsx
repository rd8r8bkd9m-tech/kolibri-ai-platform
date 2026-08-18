import { StyleSheet, Text, View } from "react-native";
import { useMemo } from "react";

import { CircleButton } from "@/src/components/ui/CircleButton";
import { Icon } from "@/src/components/icons/Icon";
import { FontSize, FontWeight, Spacing } from "@/constants/theme";
import { useDesignTokens } from "@/hooks/use-design-tokens";
import { fmtQty } from "@/src/utils/format";

type StepperProps = {
	value: number;
	onChange: (value: number) => void;
	step?: number;
	min?: number;
};

export function Stepper({ value, onChange, step = 1, min = 0 }: StepperProps) {
	const { colors } = useDesignTokens();
	const styles = useMemo(() => createStyles(colors), [colors]);
	return (
		<View style={styles.row}>
			<CircleButton
				accessibilityLabel="Уменьшить"
				onPress={() => onChange(Math.max(min, Number((value - step).toFixed(4))))}
				size={40}
				variant="outline"
			>
				<Icon color={colors.textPrimary} name="minus" size={20} />
			</CircleButton>
			<Text accessibilityLabel={`Количество ${fmtQty(value)}`} style={styles.value}>
				{fmtQty(value)}
			</Text>
			<CircleButton
				accessibilityLabel="Увеличить"
				onPress={() => onChange(Number((value + step).toFixed(4)))}
				size={40}
				variant="outline"
			>
				<Icon color={colors.textPrimary} name="plus" size={20} />
			</CircleButton>
		</View>
	);
}

type StepperColors = ReturnType<typeof useDesignTokens>["colors"];

const createStyles = (colors: StepperColors) =>
	StyleSheet.create({
		row: { alignItems: "center", flexDirection: "row", gap: Spacing.md },
		value: {
			color: colors.textPrimary,
			fontSize: FontSize.text,
			fontWeight: FontWeight.bold,
			minWidth: 48,
			textAlign: "center",
		},
	});

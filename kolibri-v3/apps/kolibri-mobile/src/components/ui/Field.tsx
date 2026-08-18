import {
	StyleSheet,
	Text,
	TextInput,
	View,
	type KeyboardTypeOptions,
} from "react-native";
import { useMemo } from "react";

import { FontSize, Spacing } from "@/constants/theme";
import { useDesignTokens } from "@/hooks/use-design-tokens";

type FieldProps = {
	label: string;
	value: string;
	onChangeText: (value: string) => void;
	placeholder?: string;
	multiline?: boolean;
	keyboardType?: KeyboardTypeOptions;
	suffix?: string;
	autoFocus?: boolean;
	maxLength?: number;
};

export function Field({
	label,
	value,
	onChangeText,
	placeholder,
	multiline,
	keyboardType,
	suffix,
	autoFocus,
	maxLength,
}: FieldProps) {
	const { colors, radii, typography } = useDesignTokens();
	const styles = useMemo(() => createStyles(colors, radii, typography), [colors, radii, typography]);
	return (
		<View style={styles.wrap}>
			<Text style={styles.label}>{label}</Text>
			<View style={styles.inputRow}>
				<TextInput
					accessibilityLabel={label}
					autoFocus={autoFocus}
					keyboardType={keyboardType}
					maxLength={maxLength}
					multiline={multiline}
					onChangeText={onChangeText}
					placeholder={placeholder}
					placeholderTextColor={colors.placeholder}
					style={[styles.input, multiline && styles.multiline]}
					value={value}
				/>
				{suffix ? <Text style={styles.suffix}>{suffix}</Text> : null}
			</View>
		</View>
	);
}

type FieldTokens = ReturnType<typeof useDesignTokens>;

const createStyles = (
	colors: FieldTokens["colors"],
	radii: FieldTokens["radii"],
	typography: FieldTokens["typography"],
) =>
	StyleSheet.create({
		wrap: { gap: Spacing.sm },
		label: { ...typography.label, color: colors.textTertiary },
		inputRow: {
			alignItems: "center",
			backgroundColor: colors.surface,
			borderColor: colors.borderLight,
			borderRadius: radii.input,
			borderWidth: 1,
			flexDirection: "row",
		},
		input: {
			color: colors.textPrimary,
			flex: 1,
			fontSize: FontSize.body,
			minHeight: 52,
			paddingHorizontal: Spacing.lg,
			paddingVertical: Spacing.md,
		},
		multiline: { minHeight: 84, textAlignVertical: "top" },
		suffix: {
			color: colors.textTertiary,
			fontSize: FontSize.medium,
			marginRight: Spacing.lg,
		},
	});

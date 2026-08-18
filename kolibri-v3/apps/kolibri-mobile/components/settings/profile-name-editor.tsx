import {
	ActivityIndicator,
	Platform,
	Pressable,
	StyleSheet,
	Text,
	TextInput,
	View,
} from "react-native";

import {
	FontSize,
	FontWeight,
	LineHeight,
	Radius,
	Spacing,
} from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";

type ProfileNameEditorProps = {
	canSave: boolean;
	error: string | null;
	onChangeText: (value: string) => void;
	onSave: () => void;
	saving: boolean;
	value: string;
};

export function ProfileNameEditor({
	canSave,
	error,
	onChangeText,
	onSave,
	saving,
	value,
}: ProfileNameEditorProps) {
	const { colors } = useTheme();
	return (
		<View style={styles.root}>
			<Text style={[styles.label, { color: colors.mutedForeground }]}>Имя</Text>
			<TextInput
				accessibilityLabel="Имя профиля"
				autoCapitalize="words"
				maxLength={160}
				onChangeText={onChangeText}
				returnKeyType="done"
				style={[
					styles.input,
					{
						backgroundColor: colors.background,
						borderColor: error ? colors.destructive : colors.border,
						color: colors.foreground,
					},
				]}
				value={value}
			/>
			{error ? (
				<Text
					accessibilityLiveRegion="polite"
					style={[styles.error, { color: colors.destructive }]}
				>
					{error}
				</Text>
			) : null}
			{canSave || saving ? (
				<Pressable
					accessibilityLabel="Сохранить профиль"
					accessibilityRole="button"
					accessibilityState={{ busy: saving, disabled: saving }}
					disabled={saving}
					onPress={onSave}
					style={({ pressed }) => [
						styles.save,
						{ backgroundColor: colors.foreground },
						pressed && styles.pressed,
					]}
				>
					{saving ? (
						<ActivityIndicator color={colors.primaryForeground} />
					) : (
						<Text style={[styles.saveText, { color: colors.primaryForeground }]}>
							Сохранить изменения
						</Text>
					)}
				</Pressable>
			) : null}
		</View>
	);
}

const styles = StyleSheet.create({
	root: { padding: Spacing.lg },
	label: {
		fontSize: FontSize.caption,
		fontWeight: FontWeight.semibold,
		lineHeight: LineHeight.footnote,
		marginBottom: Spacing.sm,
	},
	input: {
		borderRadius: Radius.md,
		borderWidth: StyleSheet.hairlineWidth,
		fontSize: FontSize.body,
		lineHeight: LineHeight.base,
		minHeight: 48,
		paddingHorizontal: Spacing.lg,
		...Platform.select({
			web: { outlineStyle: "none" } as never,
			default: {},
		}),
	},
	error: {
		fontSize: FontSize.footnote,
		lineHeight: LineHeight.compact,
		marginTop: Spacing.sm,
	},
	save: {
		alignItems: "center",
		borderRadius: Radius.circle,
		justifyContent: "center",
		marginTop: Spacing.md,
		minHeight: 46,
	},
	saveText: {
		fontSize: FontSize.medium,
		fontWeight: FontWeight.bold,
		lineHeight: LineHeight.normal,
	},
	pressed: { opacity: 0.7 },
});

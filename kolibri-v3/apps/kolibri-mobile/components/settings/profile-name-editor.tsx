import {
	ActivityIndicator,
	Platform,
	Pressable,
	StyleSheet,
	Text,
	TextInput,
	View,
} from "react-native";

import { Radius } from "@/constants/theme";
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
	root: { padding: 14 },
	label: { fontSize: 12, fontWeight: "600", lineHeight: 17, marginBottom: 6 },
	input: {
		borderRadius: Radius.md,
		borderWidth: StyleSheet.hairlineWidth,
		fontSize: 16,
		lineHeight: 21,
		minHeight: 48,
		paddingHorizontal: 13,
		...Platform.select({
			web: { outlineStyle: "none" } as never,
			default: {},
		}),
	},
	error: { fontSize: 13, lineHeight: 18, marginTop: 7 },
	save: {
		alignItems: "center",
		borderRadius: Radius.circle,
		justifyContent: "center",
		marginTop: 12,
		minHeight: 46,
	},
	saveText: { fontSize: 15, fontWeight: "700", lineHeight: 20 },
	pressed: { opacity: 0.7 },
});

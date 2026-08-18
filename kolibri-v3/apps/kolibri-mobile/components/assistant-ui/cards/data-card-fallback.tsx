import { StyleSheet, Text, View } from "react-native";

import { Radius } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";

export function DataCardFallback({ name }: { name: string }) {
	const { colors } = useTheme();
	return (
		<View
			accessibilityRole="alert"
			style={[
				styles.root,
				{
					backgroundColor: colors.surface,
					borderColor: colors.border,
				},
			]}
		>
			<Text style={[styles.title, { color: colors.foreground }]}>
				Неподдерживаемый тип данных
			</Text>
			<Text style={[styles.body, { color: colors.mutedForeground }]}>
				Клиент получил тип «{name}», для которого нет встроенного
				рендерера. Сообщение сохранено на сервере.
			</Text>
		</View>
	);
}

const styles = StyleSheet.create({
	root: {
		borderRadius: Radius.md,
		borderWidth: StyleSheet.hairlineWidth,
		maxWidth: 320,
		padding: 12,
	},
	title: { fontSize: 14, fontWeight: "700" },
	body: { fontSize: 13, lineHeight: 18, marginTop: 4 },
});

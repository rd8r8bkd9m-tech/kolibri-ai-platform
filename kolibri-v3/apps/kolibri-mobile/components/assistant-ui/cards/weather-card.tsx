import { StyleSheet, Text, View } from "react-native";

import { Icon } from "@/src/components/icons/Icon";
import { Radius } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { parseWeatherCard } from "@/src/product-chat/cards";

export function WeatherCard({ data }: { data: unknown }) {
	const { colors } = useTheme();
	const weather = parseWeatherCard(data);
	if (!weather) {
		return (
			<View
				accessibilityRole="alert"
				style={[
					styles.invalid,
					{
						backgroundColor: colors.destructiveSurface,
						borderColor: colors.destructive,
					},
				]}
			>
				<Text style={[styles.invalidText, { color: colors.destructive }]}>
					Не удалось прочитать карточку погоды
				</Text>
			</View>
		);
	}
	return (
		<View
			accessibilityLabel={`Погода: ${weather.location}, ${weather.temperatureC}°`}
			style={[
				styles.card,
				{
					backgroundColor: colors.surface,
					borderColor: colors.border,
				},
			]}
		>
			<View style={styles.heading}>
				<View
					style={[
						styles.pill,
						{ backgroundColor: colors.surfaceRaised, borderColor: colors.border },
					]}
				>
					<Text style={[styles.pillText, { color: colors.foreground }]}>
						{Math.round(weather.temperatureC)}°
					</Text>
				</View>
				<View style={styles.headingCopy}>
					<Text style={[styles.condition, { color: colors.foreground }]}>
						{weather.condition}
					</Text>
					<Text style={[styles.location, { color: colors.mutedForeground }]}>
						{weather.location}
					</Text>
				</View>
			</View>
			<View style={[styles.rows, { borderTopColor: colors.border }]}>
				{weather.forecast.map((row, index) => (
					<View
						key={`${row.day}-${index}`}
						style={[
							styles.row,
							index > 0 && { borderTopColor: colors.border },
							index > 0 && styles.rowDivider,
						]}
					>
						<Icon name="model" size={14} color={colors.mutedForeground} />
						<Text style={[styles.day, { color: colors.foreground }]}>
							{row.day}
						</Text>
						<Text style={[styles.temps, { color: colors.mutedForeground }]}>
							{Math.round(row.highC)}° / {Math.round(row.lowC)}°
						</Text>
					</View>
				))}
			</View>
		</View>
	);
}

const styles = StyleSheet.create({
	card: {
		borderRadius: Radius.card,
		borderWidth: StyleSheet.hairlineWidth,
		maxWidth: 320,
		padding: 14,
	},
	heading: { alignItems: "center", flexDirection: "row", gap: 11 },
	pill: {
		alignItems: "center",
		borderRadius: 999,
		borderWidth: StyleSheet.hairlineWidth,
		height: 38,
		justifyContent: "center",
		width: 54,
	},
	pillText: { fontSize: 17, fontWeight: "700" },
	headingCopy: { flex: 1, minWidth: 0 },
	condition: { fontSize: 16, fontWeight: "700", lineHeight: 20 },
	location: { fontSize: 13, marginTop: 2 },
	rows: {
		borderTopWidth: StyleSheet.hairlineWidth,
		marginTop: 12,
		paddingTop: 4,
	},
	row: {
		alignItems: "center",
		flexDirection: "row",
		minHeight: 34,
	},
	rowDivider: { borderTopWidth: StyleSheet.hairlineWidth },
	day: { flex: 1, fontSize: 14, fontWeight: "700", marginLeft: 9 },
	temps: { fontSize: 13, fontVariant: ["tabular-nums"] },
	invalid: {
		borderRadius: Radius.md,
		borderWidth: StyleSheet.hairlineWidth,
		maxWidth: 320,
		padding: 10,
	},
	invalidText: { fontSize: 13, lineHeight: 18 },
});

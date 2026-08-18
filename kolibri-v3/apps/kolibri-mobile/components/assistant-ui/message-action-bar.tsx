import * as Clipboard from "expo-clipboard";
import { StyleSheet, View } from "react-native";
import { ActionBarPrimitive } from "@assistant-ui/react-native";

import { Icon } from "@/src/components/icons/Icon";
import { Radius, Spacing } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";

export function MessageActionBar() {
	const { colors } = useTheme();
	const buttonStyle = ({ pressed }: { pressed: boolean }) => [
		styles.button,
		pressed && { backgroundColor: colors.muted },
	];

	return (
		<View style={styles.root}>
			<ActionBarPrimitive.Copy
				accessibilityLabel="Копировать ответ"
				copyToClipboard={async (text) => {
					await Clipboard.setStringAsync(text);
				}}
				onPressIn={haptics.selection}
				style={buttonStyle}
			>
				{({ isCopied }) => (
					<Icon
						name={isCopied ? "check" : "copy"}
						size={17}
						color={isCopied ? colors.foreground : colors.mutedForeground}
					/>
				)}
			</ActionBarPrimitive.Copy>
			<ActionBarPrimitive.Reload
				accessibilityLabel="Повторить ответ"
				onPressIn={haptics.selection}
				style={buttonStyle}
			>
				<Icon name="reload" size={17} color={colors.mutedForeground} />
			</ActionBarPrimitive.Reload>
		</View>
	);
}

const styles = StyleSheet.create({
	root: { alignItems: "center", flexDirection: "row", gap: Spacing.xs },
	button: { borderRadius: Radius.sm, padding: Spacing.sm },
});

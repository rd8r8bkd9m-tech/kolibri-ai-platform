import { useMemo, type PropsWithChildren } from "react";
import {
	Pressable,
	StyleSheet,
	type StyleProp,
	type PressableProps,
	type ViewStyle,
} from "react-native";

import { useDesignTokens } from "@/hooks/use-design-tokens";

type CircleButtonProps = PropsWithChildren<
	Omit<PressableProps, "style"> & {
		variant?: "outline" | "muted";
		size?: number;
		style?: StyleProp<ViewStyle>;
	}
>;

export function CircleButton({
	children,
	variant = "outline",
	size = 40,
	style,
	...props
}: CircleButtonProps) {
	const { colors } = useDesignTokens();
	const styles = useMemo(() => createStyles(colors), [colors]);
	return (
		<Pressable
			{...props}
			hitSlop={4}
			style={({ pressed }) => [
				styles.root,
				{
					width: size,
					height: size,
					borderRadius: size / 2,
					backgroundColor: variant === "muted" ? colors.surfaceMuted : "transparent",
				},
				pressed && styles.pressed,
				style,
			]}
		>
			{children}
		</Pressable>
	);
}

type CircleButtonColors = ReturnType<typeof useDesignTokens>["colors"];

const createStyles = (colors: CircleButtonColors) =>
	StyleSheet.create({
		root: {
			alignItems: "center",
			borderColor: colors.borderLight,
			borderWidth: 1,
			justifyContent: "center",
		},
		pressed: { opacity: 0.8, transform: [{ scale: 0.97 }] },
	});

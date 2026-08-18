import { useMemo, type ReactNode } from "react";
import {
	Dimensions,
	KeyboardAvoidingView,
	Modal,
	Platform,
	Pressable,
	ScrollView,
	StyleSheet,
	View,
} from "react-native";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import { runOnJS } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Spacing } from "@/constants/theme";
import { useDesignTokens } from "@/hooks/use-design-tokens";

type BottomSheetProps = {
	visible: boolean;
	snap?: "view" | "edit";
	onClose: () => void;
	children: ReactNode;
};

export function BottomSheet({
	visible,
	onClose,
	children,
}: BottomSheetProps) {
	const insets = useSafeAreaInsets();
	const { colors, radii } = useDesignTokens();
	const styles = useMemo(() => createStyles(colors, radii), [colors, radii]);
	const windowHeight = Dimensions.get("window").height;
	const height = windowHeight * 0.92;

	const pan = Gesture.Pan().onEnd((event) => {
		if (event.translationY > 80) {
			runOnJS(onClose)();
		}
	});

	return (
		<Modal
			animationType="none"
			onRequestClose={onClose}
			transparent
			visible={visible}
		>
			<View style={styles.root}>
				<Pressable
					accessibilityLabel="Закрыть"
					onPress={onClose}
					style={styles.backdrop}
				/>
				<View
					style={[
						styles.sheet,
						{
							height,
							paddingBottom: Math.max(insets.bottom, 16),
						},
					]}
				>
					<GestureDetector gesture={pan}>
						<View style={styles.grabberZone}>
							<View style={styles.grabber} />
						</View>
					</GestureDetector>
					<KeyboardAvoidingView
						behavior={Platform.OS === "ios" ? "padding" : undefined}
						style={styles.flex}
					>
						<ScrollView
							contentContainerStyle={styles.content}
							keyboardDismissMode="interactive"
							keyboardShouldPersistTaps="handled"
							showsVerticalScrollIndicator={false}
						>
							{children}
						</ScrollView>
					</KeyboardAvoidingView>
				</View>
			</View>
		</Modal>
	);
}

type BottomSheetColors = ReturnType<typeof useDesignTokens>["colors"];
type BottomSheetRadii = ReturnType<typeof useDesignTokens>["radii"];

const createStyles = (colors: BottomSheetColors, radii: BottomSheetRadii) =>
	StyleSheet.create({
		root: { flex: 1 },
		backdrop: {
			backgroundColor: colors.overlay,
			bottom: 0,
			left: 0,
			position: "absolute",
			right: 0,
			top: 0,
		},
		sheet: {
			backgroundColor: colors.bg,
			borderTopLeftRadius: radii.sheet,
			borderTopRightRadius: radii.sheet,
			bottom: 0,
			left: 0,
			position: "absolute",
			right: 0,
		},
		grabberZone: {
			alignItems: "center",
			paddingBottom: Spacing.sm,
			paddingTop: Spacing.md,
		},
		grabber: {
			backgroundColor: colors.grabber,
			borderRadius: radii.full,
			height: 5,
			width: 40,
		},
		flex: { flex: 1 },
		content: {
			paddingHorizontal: Spacing.xl,
			paddingBottom: Spacing.xxl,
		},
	});

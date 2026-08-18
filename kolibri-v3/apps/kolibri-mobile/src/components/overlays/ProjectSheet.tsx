import { useEffect, useMemo, useState } from "react";
import {
	Modal,
	Pressable,
	ScrollView,
	StyleSheet,
	Text,
	TextInput,
	View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated, {
	Easing,
	useAnimatedStyle,
	useSharedValue,
	withTiming,
} from "react-native-reanimated";

import { Chip } from "@/src/components/ui/Chip";
import { CircleButton } from "@/src/components/ui/CircleButton";
import { Icon } from "@/src/components/icons/Icon";
import { COPY, PROJECT_SHEET } from "@/src/data/copy";
import {
	FontSize,
	FontWeight,
	LineHeight,
	Spacing,
} from "@/constants/theme";
import { useDesignTokens } from "@/hooks/use-design-tokens";

type ProjectSheetProps = {
	visible: boolean;
	onClose: () => void;
	onCreate?: (name: string) => void;
};

export function ProjectSheet({ visible, onClose, onCreate }: ProjectSheetProps) {
	const insets = useSafeAreaInsets();
	const { colors, radii, typography } = useDesignTokens();
	const styles = useMemo(() => createStyles(colors, radii), [colors, radii]);
	const [name, setName] = useState("");
	const translateY = useSharedValue(720);

	useEffect(() => {
		if (visible) {
			translateY.value = 720;
			translateY.value = withTiming(0, {
				duration: 300,
				easing: Easing.out(Easing.cubic),
			});
		}
	}, [translateY, visible]);

	const sheetStyle = useAnimatedStyle(() => ({
		transform: [{ translateY: translateY.value }],
	}));

	const create = () => {
		if (!name.trim()) return;
		onCreate?.(name.trim());
		setName("");
		onClose();
	};

	return (
		<Modal
			animationType="none"
			onRequestClose={onClose}
			transparent
			visible={visible}
		>
			<View style={styles.modal}>
				<Pressable
					accessibilityLabel={COPY.closeLabel}
					onPress={onClose}
					style={styles.backdrop}
				/>
				<Animated.View
					accessibilityViewIsModal
					style={[
						styles.sheet,
						{ paddingBottom: Math.max(insets.bottom, 20) },
						sheetStyle,
					]}
				>
					<View style={styles.header}>
						<Text
							accessibilityRole="header"
							style={[typography.hSheet, styles.headerTitle]}
						>
							{PROJECT_SHEET.title}
						</Text>
						<CircleButton
							accessibilityLabel={COPY.closeLabel}
							size={48}
							variant="outline"
							onPress={onClose}
						>
							<Icon name="close" size={24} color={colors.textPrimary} />
						</CircleButton>
					</View>

					<Text style={[typography.body, styles.description]}>
						{PROJECT_SHEET.description}
					</Text>

					<View style={styles.input}>
						<Icon name="smile" size={24} color={colors.textPrimary} />
						<TextInput
							accessibilityLabel={PROJECT_SHEET.inputPlaceholder}
							autoFocus
							onChangeText={setName}
							placeholder={PROJECT_SHEET.inputPlaceholder}
							placeholderTextColor={colors.placeholder}
							style={styles.inputText}
							value={name}
						/>
					</View>

					<ScrollView
						contentContainerStyle={styles.chips}
						horizontal
						showsHorizontalScrollIndicator={false}
					>
						{PROJECT_SHEET.chips.map((chip) => (
							<Chip
								key={chip.label}
								icon={chip.icon}
								iconColor={chip.color}
								label={chip.label}
							/>
						))}
					</ScrollView>

					<Pressable
						accessibilityRole="button"
						accessibilityLabel={PROJECT_SHEET.cta}
						accessibilityState={{ disabled: !name.trim() }}
						disabled={!name.trim()}
						onPress={create}
						style={({ pressed }) => [
							styles.cta,
							{
								backgroundColor: name.trim()
									? colors.textPrimary
									: colors.disabled,
							},
							pressed && styles.pressed,
						]}
					>
						<Text style={styles.ctaText}>{PROJECT_SHEET.cta}</Text>
					</Pressable>
				</Animated.View>
			</View>
		</Modal>
	);
}

type ProjectSheetColors = ReturnType<typeof useDesignTokens>["colors"];
type ProjectSheetRadii = ReturnType<typeof useDesignTokens>["radii"];

const createStyles = (colors: ProjectSheetColors, radii: ProjectSheetRadii) =>
	StyleSheet.create({
		modal: { flex: 1, justifyContent: "flex-end" },
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
			paddingHorizontal: Spacing.xl,
			paddingTop: Spacing.lg,
		},
		header: {
			alignItems: "center",
			flexDirection: "row",
			height: 56,
			justifyContent: "flex-end",
		},
		headerTitle: {
			color: colors.textPrimary,
			left: 68,
			position: "absolute",
			right: 68,
			textAlign: "center",
		},
		description: {
			color: colors.textTertiary,
			lineHeight: LineHeight.relaxed,
			marginTop: Spacing.md,
			textAlign: "center",
		},
		input: {
			alignItems: "center",
			backgroundColor: colors.surfaceMuted,
			borderRadius: radii.input,
			flexDirection: "row",
			gap: Spacing.md,
			height: 60,
			marginTop: Spacing.xxl,
			paddingHorizontal: Spacing.lg,
		},
		inputText: {
			color: colors.textPrimary,
			flex: 1,
			fontSize: FontSize.text,
			paddingVertical: Spacing.md,
		},
		chips: { gap: Spacing.sm, paddingVertical: Spacing.lg },
		cta: {
			alignItems: "center",
			borderRadius: radii.full,
			height: 60,
			justifyContent: "center",
			marginTop: Spacing.xs,
			width: "100%",
		},
		ctaText: {
			color: colors.surface,
			fontSize: FontSize.h3,
			fontWeight: FontWeight.bold,
		},
		pressed: { opacity: 0.8, transform: [{ scale: 0.97 }] },
	});

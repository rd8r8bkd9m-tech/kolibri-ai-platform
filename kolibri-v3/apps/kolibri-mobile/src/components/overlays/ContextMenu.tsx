import { useAui } from "@assistant-ui/react-native";
import { useRouter } from "expo-router";
import { useEffect, useMemo } from "react";
import {
	Dimensions,
	Modal,
	Pressable,
	Share,
	StyleSheet,
	Text,
	View,
} from "react-native";
import Animated, {
	Easing,
	useAnimatedStyle,
	useSharedValue,
	withTiming,
} from "react-native-reanimated";

import { haptics } from "@/lib/haptics";
import { useDesignTokens } from "@/hooks/use-design-tokens";
import { Icon } from "@/src/components/icons/Icon";
import {
	FontSize,
	FontWeight,
	LineHeight,
	Spacing,
} from "@/constants/theme";
import {
	CONTEXT_MENU_ITEMS,
	COPY,
	type ContextMenuItem,
} from "@/src/data/copy";
import type { ThreadActionItem } from "@/src/data/pinned";

type ContextMenuProps = {
	anchor: { x: number; y: number } | null;
	item: ThreadActionItem | null;
	onClose: () => void;
	onNewProject?: () => void;
};

export function ContextMenu({
	anchor,
	item,
	onClose,
	onNewProject,
}: ContextMenuProps) {
	const aui = useAui();
	const router = useRouter();
	const { colors, radii } = useDesignTokens();
	const styles = useMemo(() => createStyles(colors, radii), [colors, radii]);
	const progress = useSharedValue(0);

	useEffect(() => {
		if (anchor && item) {
			progress.value = 0;
			progress.value = withTiming(1, {
				duration: 200,
				easing: Easing.out(Easing.cubic),
			});
		}
	}, [anchor, item, progress]);

	const cardStyle = useAnimatedStyle(() => ({
		opacity: progress.value,
		transform: [{ scale: 0.9 + progress.value * 0.1 }],
	}));

	const visible = Boolean(anchor && item);
	const window = Dimensions.get("window");
	const menuWidth = window.width * 0.64;
	const left = anchor
		? Math.min(Math.max(16, anchor.x - menuWidth + 24), window.width - menuWidth - 16)
		: 0;
	const top = anchor ? Math.min(anchor.y, window.height - 360) : 0;

	const runAction = (action: ContextMenuItem["action"], target: ThreadActionItem) => {
		const thread = aui.threads.item({ id: target.id });
		switch (action) {
			case "newProject":
				onNewProject?.();
				break;
			case "togglePin":
				thread.updateCustom({
					...(target.custom ?? {}),
					pinned: !target.pinned,
				});
				break;
			case "share":
				void Share.share({ message: target.title });
				break;
			case "settings":
				router.push("/account?client=mobile");
				break;
			case "delete":
				thread.delete();
				break;
		}
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
					accessibilityLabel={COPY.closeMenuLabel}
					onPress={onClose}
					style={styles.backdrop}
				/>
				<Animated.View
					accessibilityViewIsModal
					style={[styles.card, { left, top, width: menuWidth }, cardStyle]}
				>
					{CONTEXT_MENU_ITEMS.map((entry) => (
						<Pressable
							key={entry.label}
							accessibilityRole="button"
							onPress={() => {
								if (item) runAction(entry.action, item);
								haptics.medium();
								onClose();
							}}
							style={({ pressed }) => [
								styles.menuItem,
								pressed && styles.pressed,
							]}
						>
							<Icon
								name={entry.icon}
								size={24}
								color={entry.danger ? colors.danger : colors.textPrimary}
							/>
							<Text
								numberOfLines={2}
								style={[
									styles.menuLabel,
									{ color: entry.danger ? colors.danger : colors.textPrimary },
								]}
							>
								{entry.label}
							</Text>
						</Pressable>
					))}
					<View style={styles.preview}>
						<Icon name="folder" size={24} color={colors.textPrimary} />
						<Text numberOfLines={1} style={styles.previewTitle}>
							{item?.title ?? ""}
						</Text>
					</View>
				</Animated.View>
			</View>
		</Modal>
	);
}

type ContextMenuColors = ReturnType<typeof useDesignTokens>["colors"];
type ContextMenuRadii = ReturnType<typeof useDesignTokens>["radii"];

const createStyles = (colors: ContextMenuColors, radii: ContextMenuRadii) =>
	StyleSheet.create({
		modal: { flex: 1 },
		backdrop: {
			backgroundColor: colors.overlay,
			bottom: 0,
			left: 0,
			position: "absolute",
			right: 0,
			top: 0,
		},
		card: {
			backgroundColor: colors.card,
			borderColor: colors.borderDark,
			borderRadius: radii.card,
			borderWidth: 1,
			padding: Spacing.lg,
			position: "absolute",
		},
		menuItem: {
			alignItems: "center",
			flexDirection: "row",
			gap: Spacing.xl,
			minHeight: 52,
			paddingVertical: Spacing.lg,
		},
		menuLabel: {
			flex: 1,
			fontSize: FontSize.sheet,
			fontWeight: FontWeight.semibold,
			lineHeight: LineHeight.list,
		},
		preview: {
			alignItems: "center",
			backgroundColor: colors.card,
			borderRadius: radii.card,
			flexDirection: "row",
			gap: Spacing.md,
			marginTop: Spacing.sm,
			minHeight: 52,
			paddingHorizontal: Spacing.xs,
		},
		previewTitle: {
			color: colors.textPrimary,
			flex: 1,
			fontSize: FontSize.text,
			fontWeight: FontWeight.semibold,
		},
		pressed: { opacity: 0.8 },
	});

import { useAui, useAuiState } from "@assistant-ui/react-native";
import { useRouter, type Href } from "expo-router";
import { useDrawerStatus } from "expo-router/drawer";
import { useMemo, useRef } from "react";
import {
	Dimensions,
	ScrollView,
	StyleSheet,
	Text,
	View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated, {
	Extrapolation,
	interpolate,
	useAnimatedStyle,
	type SharedValue,
} from "react-native-reanimated";

import { haptics } from "@/lib/haptics";
import { releaseWebFocus } from "@/src/accessibility/release-web-focus";
import { useMobileSession } from "@/src/auth/mobile-session";
import { FontSize, FontWeight, Layout, Spacing } from "@/constants/theme";
import { useDesignTokens } from "@/hooks/use-design-tokens";
import { Icon } from "@/src/components/icons/Icon";
import { CircleButton } from "@/src/components/ui/CircleButton";
import { ListItem } from "@/src/components/ui/ListItem";
import { PillButton } from "@/src/components/ui/PillButton";
import { SectionHeader } from "@/src/components/ui/SectionHeader";
import { COPY } from "@/src/data/copy";
import { MENU } from "@/src/data/menu";
import type { ThreadActionItem } from "@/src/data/pinned";

type SidebarProps = {
	progress?: SharedValue<number>;
	onClose: () => void;
	onOpenSheet?: () => void;
	onOpenContextMenu: (
		item: ThreadActionItem,
		anchor: { x: number; y: number },
	) => void;
};

function profileInitials(name: string) {
	return (
		name
			.split(/\s+/)
			.map((part) => part.trim())
			.filter(Boolean)
			.slice(0, 2)
			.map((part) => part[0]?.toLocaleUpperCase("ru-RU") ?? "")
			.join("") || "К"
	);
}

function ThreadRow({
	item,
	onClose,
	onOpenContextMenu,
}: {
	item: ThreadActionItem;
	onClose: () => void;
	onOpenContextMenu: SidebarProps["onOpenContextMenu"];
}) {
	const aui = useAui();
	const ref = useRef<View>(null);

	return (
		<View collapsable={false} ref={ref}>
			<ListItem
				icon={item.pinned ? "pin" : "messageCircle"}
				onLongPress={() => {
					ref.current?.measureInWindow((x, y, width, height) => {
						onOpenContextMenu(item, { x, y: y + height });
					});
				}}
				onPress={() => {
					aui.threads.switchToThread(item.id);
					onClose();
				}}
				title={item.title}
			/>
		</View>
	);
}

export function Sidebar({
	progress,
	onClose,
	onOpenContextMenu,
}: SidebarProps) {
	const insets = useSafeAreaInsets();
	const router = useRouter();
	const aui = useAui();
	const session = useMobileSession();
	const drawerOpen = useDrawerStatus() === "open";
	const { colors, radii, typography } = useDesignTokens();
	const styles = useMemo(() => createStyles(colors, radii), [colors, radii]);
	const threadIds = useAuiState((threadState) => threadState.threads.threadIds);
	const threadItems = useAuiState(
		(threadState) => threadState.threads.threadItems,
	);
	const width = Math.min(
		Dimensions.get("window").width * Layout.drawerFraction,
		340,
	);

	const panelStyle = useAnimatedStyle(() => {
		if (!progress) return {};
		return {
			transform: [
				{
					translateX: interpolate(
						progress.value,
						[0, 1],
						[-width, 0],
						Extrapolation.CLAMP,
					),
				},
			],
		};
	});

	const rows: ThreadActionItem[] = threadIds.map((id) => {
		const thread = threadItems.find((entry) => entry.id === id);
		const pinned = thread?.custom?.pinned === true;
		return {
			id,
			title: thread?.title || "Новый диалог",
			icon: pinned ? "pin" : "messageCircle",
			pinned,
			custom: thread?.custom,
		};
	});
	const pinnedRows = rows.filter((row) => row.pinned);
	const recentRows = rows.filter((row) => !row.pinned);
	const visibleMenu = MENU.filter((entry) => {
		if (entry.capability) {
			return session.user?.capabilities.includes(entry.capability) === true;
		}
		if (entry.requireThreads) {
			return rows.length > 0;
		}
		return true;
	});

	const navigate = (path: Href) => {
		haptics.medium();
		releaseWebFocus();
		onClose();
		router.push(path);
	};

	const userName = session.user?.name ?? "Пользователь";

	const content = (
		<>
			<View style={styles.header}>
				<Text
					accessibilityRole="header"
					style={[typography.hScreen, { color: colors.textPrimary }]}
				>
					{COPY.appTitle}
				</Text>
				<CircleButton
					accessibilityLabel={COPY.searchLabel}
					onPress={() => haptics.medium()}
					size={48}
					variant="muted"
				>
					<Icon name="search" size={24} color={colors.textPrimary} />
				</CircleButton>
			</View>

			<ScrollView
				contentContainerStyle={styles.scrollContent}
				showsVerticalScrollIndicator={false}
				style={styles.scroll}
			>
				<View style={styles.menu}>
					{visibleMenu.map((entry) => (
						<ListItem
							bold
							key={entry.id}
							icon={entry.icon}
							onPress={() => navigate(`${entry.route}?client=mobile` as Href)}
							title={entry.label}
						/>
					))}
				</View>

				<SectionHeader title={COPY.sectionPinned} />
				<View style={styles.section}>
					{pinnedRows.map((item) => (
						<ThreadRow
							key={item.id}
							item={item}
							onClose={onClose}
							onOpenContextMenu={onOpenContextMenu}
						/>
					))}
				</View>

				<SectionHeader title={COPY.sectionRecent} />
				<View style={styles.section}>
					{recentRows.map((item) => (
						<ThreadRow
							key={item.id}
							item={item}
							onClose={onClose}
							onOpenContextMenu={onOpenContextMenu}
						/>
					))}
				</View>
			</ScrollView>

			<View style={styles.footer}>
				<PillButton
					filled
					icon="squarePen"
					onPress={() => {
						aui.threads.switchToNewThread();
						onClose();
					}}
					style={styles.footerChat}
					title={COPY.footerChat}
				/>
			</View>

			<View style={styles.userRow}>
				<View style={[styles.avatar, { backgroundColor: colors.textPrimary }]}>
					<Text style={[styles.avatarText, { color: colors.surface }]}>
						{profileInitials(userName)}
					</Text>
				</View>
				<Text numberOfLines={1} style={[styles.userName, { color: colors.textPrimary }]}>
					{userName}
				</Text>
				<CircleButton
					accessibilityLabel={COPY.settingsLabel}
					onPress={() => navigate("/account?client=mobile")}
					size={44}
					variant="outline"
				>
					<Icon name="settings" size={22} color={colors.textPrimary} />
				</CircleButton>
			</View>
		</>
	);

	if (!progress) {
		// Static mode for expo-router Drawer
		return (
			<View
				accessibilityElementsHidden={!drawerOpen}
				accessibilityViewIsModal={drawerOpen}
				importantForAccessibility={
					drawerOpen ? "yes" : "no-hide-descendants"
				}
				style={[
					styles.panel,
					{
						paddingBottom: Math.max(insets.bottom, Spacing.md),
						paddingTop: insets.top + Spacing.lg,
						width,
					},
				]}
			>
				{content}
			</View>
		);
	}

	// Animated mode for custom overlay
	return (
		<Animated.View
			accessibilityElementsHidden={!drawerOpen}
			accessibilityViewIsModal={drawerOpen}
			importantForAccessibility={
				drawerOpen ? "yes" : "no-hide-descendants"
			}
			style={[
				styles.panel,
				{
					paddingBottom: Math.max(insets.bottom, Spacing.md),
					paddingTop: insets.top + Spacing.lg,
					width,
				},
				panelStyle,
			]}
		>
			{content}
		</Animated.View>
	);
}

type SidebarColors = ReturnType<typeof useDesignTokens>["colors"];
type SidebarRadii = ReturnType<typeof useDesignTokens>["radii"];

const createStyles = (colors: SidebarColors, radii: SidebarRadii) =>
	StyleSheet.create({
		panel: {
			backgroundColor: colors.bg,
			bottom: 0,
			left: 0,
			paddingHorizontal: Spacing.xl,
			position: "absolute",
			top: 0,
		},
		header: {
			alignItems: "center",
			flexDirection: "row",
			justifyContent: "space-between",
		},
		scroll: { flex: 1, marginTop: Spacing.sm },
		scrollContent: { paddingBottom: Spacing.lg },
		menu: { marginTop: Spacing.md },
		section: { gap: Spacing.xs },
		footer: {
			borderTopColor: colors.borderLight,
			borderTopWidth: StyleSheet.hairlineWidth,
			paddingTop: Spacing.md,
		},
		footerChat: { width: "100%" },
		userRow: {
			alignItems: "center",
			flexDirection: "row",
			gap: Spacing.md,
			marginTop: Spacing.md,
		},
		avatar: {
			alignItems: "center",
			borderRadius: radii.full,
			height: 44,
			justifyContent: "center",
			width: 44,
		},
		avatarText: { fontSize: FontSize.text, fontWeight: FontWeight.bold },
		userName: {
			flex: 1,
			fontSize: FontSize.text,
			fontWeight: FontWeight.semibold,
		},
	});

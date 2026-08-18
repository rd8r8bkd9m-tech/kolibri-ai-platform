import { useAui } from "@assistant-ui/react-native";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
	ActivityIndicator,
	FlatList,
	Pressable,
	StyleSheet,
	Text,
	TextInput,
	View,
} from "react-native";

import { NativeScreenShell } from "@/components/shell/native-screen-shell";
import { CircleButton } from "@/components/shell/circle-button";
import { SurfaceBoundary } from "@/components/shell/surface-boundary";
import { Icon } from "@/src/components/icons/Icon";
import {
	FontSize,
	FontWeight,
	Layout,
	LetterSpacing,
	LineHeight,
	Radius,
	Spacing,
	typography,
} from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";
import { API_BASE_URL, useMobileSession } from "@/src/auth/mobile-session";
import { ProductChatClient } from "@/src/product-chat/client";
import type { ProductThread } from "@/src/product-chat/contracts";
import { constructionEstimateAccess } from "@/src/verticals/construction-estimates/access";

type ProjectGroup = {
	projectId: string;
	threads: readonly ProductThread[];
	contextName: string | null;
	latest: ProductThread;
};

const shortProjectId = (projectId: string) => {
	const marker = projectId.startsWith("project_") ? "project_" : "";
	const rest = projectId.slice(marker.length);
	return `${marker}${rest.slice(0, 14)}…`;
};

export default function ProjectsScreen() {
	const router = useRouter();
	const aui = useAui();
	const session = useMobileSession();
	const { colors } = useTheme();
	const estimateAccess = constructionEstimateAccess(session.user);
	const client = useMemo(
		() => new ProductChatClient(session.authorizedFetch),
		[session.authorizedFetch],
	);
	const [groups, setGroups] = useState<readonly ProjectGroup[]>([]);
	const [query, setQuery] = useState("");
	const [status, setStatus] = useState<"loading" | "ready" | "error">(
		"loading",
	);
	const [message, setMessage] = useState("");

	const load = useCallback(async (options?: { reset?: boolean }) => {
		if (options?.reset) {
			setStatus("loading");
			setMessage("");
		}
		try {
			const threads = (await client.listThreads()).filter(
				(thread) => thread.status === "regular",
			);
			const byProject = new Map<string, ProductThread[]>();
			for (const thread of threads) {
				const bucket = byProject.get(thread.projectId) ?? [];
				bucket.push(thread);
				byProject.set(thread.projectId, bucket);
			}
			const next: ProjectGroup[] = [...byProject.entries()]
				.map(([projectId, projectThreads]) => {
					const sorted = [...projectThreads].sort((a, b) =>
						b.updatedAt.localeCompare(a.updatedAt),
					);
					return {
						projectId,
						threads: sorted,
						contextName: null,
						latest: sorted[0],
					};
				})
				.sort((a, b) => b.latest.updatedAt.localeCompare(a.latest.updatedAt));
			setGroups(next);

			if (estimateAccess.enabled) {
				const named = await Promise.all(
					next.slice(0, 20).map(async (group) => {
						try {
							const response = await session.authorizedFetch(
								`${API_BASE_URL}/v1/projects/${encodeURIComponent(group.projectId)}/context`,
								{ headers: { Accept: "application/json" } },
							);
							if (!response.ok) return group;
							const value = (await response.json()) as {
								project?: { name?: unknown };
							};
							const name = value.project?.name;
							return typeof name === "string" && name.trim()
								? { ...group, contextName: name.trim() }
								: group;
						} catch {
							return group;
						}
					}),
				);
				setGroups(named);
			}
			setStatus("ready");
		} catch (reason) {
			setMessage(
				reason instanceof Error
					? reason.message
					: "Не удалось загрузить проекты.",
			);
			setStatus("error");
		}
	}, [client, estimateAccess.enabled, session]);

	useEffect(() => {
		const timer = setTimeout(() => void load(), 0);
		return () => clearTimeout(timer);
	}, [load]);

	const openProject = (group: ProjectGroup) => {
		haptics.selection();
		aui.threads.switchToThread(group.latest.id);
		router.replace("/app?client=mobile");
	};

	const newChat = () => {
		haptics.selection();
		aui.threads.switchToNewThread();
		router.replace("/app?client=mobile");
	};

	const normalizedQuery = query.trim().toLowerCase();
	const visibleGroups = normalizedQuery
		? groups.filter((group) => {
				const name =
					group.contextName ??
					`${shortProjectId(group.projectId)} ${group.latest.title}`;
				return name.toLowerCase().includes(normalizedQuery);
			})
		: groups;

	return (
		<NativeScreenShell
			onBack={() => router.replace("/app?client=mobile")}
			title="Проекты"
			trailing={
				<CircleButton
					accessibilityLabel="Новая задача"
					accessibilityRole="button"
					onPress={newChat}
				>
					<Icon name="plus" size={24} color={colors.foreground} />
				</CircleButton>
			}
		>
			{status === "loading" ? (
				<View accessibilityLabel="Загрузка проектов" style={styles.center}>
					<ActivityIndicator color={colors.foreground} />
				</View>
			) : status === "error" ? (
				<View style={styles.center}>
					<Text
						accessibilityRole="alert"
						style={[styles.errorText, { color: colors.destructive }]}
					>
						{message}
					</Text>
					<Pressable
						accessibilityRole="button"
						onPress={() => void load({ reset: true })}
						style={[styles.retry, { backgroundColor: colors.surface }]}
					>
						<Icon name="reload" color={colors.foreground} size={19} />
						<Text
							style={[styles.retryText, { color: colors.foreground }]}
						>
							Повторить
						</Text>
					</Pressable>
				</View>
			) : groups.length === 0 ? (
				<SurfaceBoundary
					body="Задачи, созданные в чате, сгруппируются по проектам сервера."
					icon="folder"
					note="Создайте первую задачу в чате — проект появится здесь."
					title="Проектов пока нет"
				/>
			) : (
				<FlatList
					contentContainerStyle={styles.list}
					data={visibleGroups}
					keyExtractor={(group) => group.projectId}
					renderItem={({ item }) => (
						<Pressable
							accessibilityHint="Открывает последнюю задачу проекта"
							accessibilityLabel={`${item.contextName ?? shortProjectId(item.projectId)}, ${item.threads.length} задач`}
							accessibilityRole="button"
							onPress={() => openProject(item)}
							style={({ pressed }) => [
								styles.projectCard,
								{ backgroundColor: colors.surface },
								pressed && styles.pressed,
							]}
						>
							<View style={styles.projectIcon}>
								<Icon name="folder" color={colors.foreground} size={25} />
							</View>
							<View style={styles.projectCopy}>
								<Text
									numberOfLines={1}
									style={[
										typography.projectName,
										styles.projectName,
										{ color: colors.foreground },
									]}
								>
									{item.contextName ?? shortProjectId(item.projectId)}
								</Text>
								<Text
									numberOfLines={1}
									style={[
										typography.projectMeta,
										styles.projectMeta,
										{ color: colors.mutedForeground },
									]}
								>
									{item.threads.length} задач · {item.latest.title}
								</Text>
							</View>
							<Icon
								name="chevron-right"
								color={colors.mutedForeground}
								size={22}
							/>
						</Pressable>
					)}
					showsVerticalScrollIndicator={false}
				/>
			)}
			{status === "ready" && groups.length > 0 ? (
				<View style={[styles.searchBar, { borderTopColor: colors.muted }]}>
					<View style={[styles.search, { backgroundColor: colors.surface }]}>
						<Icon name="search" size={18} color={colors.mutedForeground} />
						<TextInput
							accessibilityLabel="Поиск по проектам"
							autoCorrect={false}
							onChangeText={setQuery}
							placeholder="Поиск проектов"
							placeholderTextColor={colors.mutedForeground}
							returnKeyType="search"
							style={[styles.searchInput, { color: colors.foreground }]}
							value={query}
						/>
						{query ? (
							<Pressable
								accessibilityLabel="Очистить поиск"
								accessibilityRole="button"
								hitSlop={8}
								onPress={() => setQuery("")}
								style={styles.searchClear}
							>
								<Icon name="close" size={16} color={colors.mutedForeground} />
							</Pressable>
						) : null}
					</View>
				</View>
			) : null}
		</NativeScreenShell>
	);
}

const styles = StyleSheet.create({
	safe: { flex: 1 },
	center: {
		alignItems: "center",
		flex: 1,
		justifyContent: "center",
		paddingHorizontal: Spacing.xxl,
	},
	errorText: {
		fontSize: FontSize.small,
		lineHeight: LineHeight.normal,
		textAlign: "center",
	},
	retry: {
		alignItems: "center",
		borderRadius: Radius.control,
		flexDirection: "row",
		gap: Spacing.sm,
		marginTop: Spacing.lg,
		minHeight: 44,
		paddingHorizontal: Layout.composerInset,
	},
	retryText: { fontSize: FontSize.medium, fontWeight: FontWeight.bold },
	list: { gap: Spacing.md, padding: Spacing.lg, paddingBottom: Spacing.xxl },
	projectCard: {
		alignItems: "center",
		borderRadius: Radius.card,
		flexDirection: "row",
		minHeight: 78,
		paddingHorizontal: Spacing.lg,
		paddingVertical: Spacing.md,
	},
	projectIcon: {
		alignItems: "center",
		height: 44,
		justifyContent: "center",
		width: 44,
	},
	projectCopy: {
		flex: 1,
		marginLeft: Spacing.sm,
		marginRight: Spacing.sm,
		minWidth: 0,
	},
	projectName: { letterSpacing: LetterSpacing.relaxed },
	projectMeta: { marginTop: Spacing.xs },
	pressed: { opacity: 0.58 },
	searchBar: {
		borderTopWidth: StyleSheet.hairlineWidth,
		paddingBottom: Spacing.sm,
		paddingHorizontal: Spacing.lg,
		paddingTop: Spacing.md,
	},
	search: {
		alignItems: "center",
		borderRadius: Radius.md,
		flexDirection: "row",
		gap: Spacing.sm,
		minHeight: 42,
		paddingHorizontal: Spacing.md,
	},
	searchInput: {
		flex: 1,
		fontSize: FontSize.medium,
		minHeight: 42,
		paddingVertical: Spacing.sm,
	},
	searchClear: {
		alignItems: "center",
		height: 28,
		justifyContent: "center",
		width: 28,
	},
});

import { useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
	ActivityIndicator,
	FlatList,
	Pressable,
	StyleSheet,
	Text,
	View,
} from "react-native";

import { NativeScreenShell } from "@/components/shell/native-screen-shell";
import { Icon } from "@/src/components/icons/Icon";
import { DocumentsClient } from "@/src/backend/documents/client";
import type { DocumentSummary } from "@/src/backend/documents/contracts";
import {
	FontSize,
	FontWeight,
	Radius,
	Spacing,
} from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { useMobileSession } from "@/src/auth/mobile-session";
import { constructionEstimateAccess } from "@/src/verticals/construction-estimates/access";

export default function LibraryScreen() {
	const router = useRouter();
	const { colors } = useTheme();
	const session = useMobileSession();
	const access = constructionEstimateAccess(session.user);
	const client = useMemo(
		() => new DocumentsClient(session.authorizedFetch),
		[session.authorizedFetch],
	);
	const [documents, setDocuments] = useState<readonly DocumentSummary[]>([]);
	const [status, setStatus] = useState<"loading" | "ready" | "error">(
		"loading",
	);
	const [message, setMessage] = useState("");
	const [selected, setSelected] = useState<DocumentSummary | null>(null);

	const load = useCallback(async () => {
		try {
			setDocuments(await client.list());
			setStatus("ready");
		} catch (reason) {
			setMessage(
				reason instanceof Error
					? reason.message
					: "Не удалось загрузить документы.",
			);
			setStatus("error");
		}
	}, [client]);

	useEffect(() => {
		if (!access.enabled) return;
		const timer = setTimeout(() => void load(), 0);
		return () => clearTimeout(timer);
	}, [access.enabled, load]);

	const openDocument = (document: DocumentSummary) => {
		if (document.kind === "estimate") {
			router.replace(
				`/estimate/${encodeURIComponent(document.projectId)}?client=mobile`,
			);
			return;
		}
		setSelected(document);
	};

	return (
		<NativeScreenShell
			onBack={() => router.replace("/app?client=mobile")}
			title="Документы"
		>
			{selected ? (
				<View style={styles.viewer}>
					<Pressable
						accessibilityRole="button"
						onPress={() => setSelected(null)}
						style={styles.viewerBack}
					>
						<Icon name="chevron-left" color={colors.foreground} size={22} />
						<Text style={[styles.viewerBackText, { color: colors.foreground }]}>
							К документам
						</Text>
					</Pressable>
					<Text style={[styles.viewerTitle, { color: colors.foreground }]}>
						{selected.name}
					</Text>
					<View style={styles.viewerRow}>
						<Text style={[styles.viewerLabel, { color: colors.mutedForeground }]}>
							Проект
						</Text>
						<Text style={[styles.viewerValue, { color: colors.foreground }]}>
							{selected.projectName}
						</Text>
					</View>
					<View style={styles.viewerRow}>
						<Text style={[styles.viewerLabel, { color: colors.mutedForeground }]}>
							Тип
						</Text>
						<Text style={[styles.viewerValue, { color: colors.foreground }]}>
							{selected.slotType}
						</Text>
					</View>
					<View style={styles.viewerRow}>
						<Text style={[styles.viewerLabel, { color: colors.mutedForeground }]}>
							Статус
						</Text>
						<Text style={[styles.viewerValue, { color: colors.foreground }]}>
							{selected.status}
						</Text>
					</View>
					<View style={styles.viewerRow}>
						<Text style={[styles.viewerLabel, { color: colors.mutedForeground }]}>
							Версия
						</Text>
						<Text style={[styles.viewerValue, { color: colors.foreground }]}>
							{selected.version}
						</Text>
					</View>
					{selected.total ? (
						<View style={styles.viewerRow}>
							<Text style={[styles.viewerLabel, { color: colors.mutedForeground }]}>
								Сумма
							</Text>
							<Text style={[styles.viewerValue, { color: colors.foreground }]}>
								{selected.total} ₽
							</Text>
						</View>
					) : null}
				</View>
			) : (
				<>
			{!access.enabled ? (
				<View style={styles.empty}>
					<Icon name="library" color={colors.mutedForeground} size={34} />
					<Text style={[styles.emptyTitle, { color: colors.foreground }]}>
						Документы недоступны
					</Text>
					<Text style={[styles.emptyBody, { color: colors.mutedForeground }]}>
						Сервер ещё не активировал доступ к документам.
					</Text>
				</View>
			) : status === "loading" ? (
				<View accessibilityLabel="Загрузка документов" style={styles.center}>
					<ActivityIndicator color={colors.foreground} />
				</View>
			) : status === "error" ? (
				<View style={styles.center}>
					<Text style={[styles.error, { color: colors.destructive }]}>
						{message}
					</Text>
					<Pressable
						accessibilityRole="button"
						onPress={() => void load()}
						style={[styles.retry, { backgroundColor: colors.surface }]}
					>
						<Icon name="reload" color={colors.foreground} size={18} />
						<Text style={[styles.retryText, { color: colors.foreground }]}>
							Повторить
						</Text>
					</Pressable>
				</View>
			) : (
				<FlatList
					contentContainerStyle={[
						styles.list,
						documents.length === 0 && styles.listEmpty,
					]}
					data={documents}
					keyExtractor={(document) => document.id}
					ListEmptyComponent={
						<View style={styles.empty}>
							<Icon name="library" color={colors.mutedForeground} size={34} />
							<Text style={[styles.emptyTitle, { color: colors.foreground }]}>
								Документов пока нет
							</Text>
							<Text style={[styles.emptyBody, { color: colors.mutedForeground }]}>
								Документы появятся после первой сметы или проекта.
							</Text>
						</View>
					}
					renderItem={({ item }) => (
						<Pressable
							accessibilityHint="Открывает документ"
							accessibilityLabel={`${item.name}, версия ${item.version}`}
							accessibilityRole="button"
							onPress={() => openDocument(item)}
							style={({ pressed }) => [
								styles.card,
								{ backgroundColor: colors.surface },
								pressed && styles.pressed,
							]}
						>
							<View style={[styles.icon, { backgroundColor: colors.infoBg }]}>
								<Icon
									name={item.kind === "estimate" ? "document" : "library"}
									color={colors.send}
									size={24}
								/>
							</View>
							<View style={styles.copy}>
								<Text numberOfLines={1} style={[styles.name, { color: colors.foreground }]}>
									{item.name}
								</Text>
								<Text numberOfLines={1} style={[styles.meta, { color: colors.mutedForeground }]}>
									{item.projectName} · v{item.version}
								</Text>
							</View>
							<Icon name="chevron-right" color={colors.mutedForeground} size={22} />
						</Pressable>
					)}
					showsVerticalScrollIndicator={false}
				/>
			)}
				</>
			)}
		</NativeScreenShell>
	);
}

const styles = StyleSheet.create({
	center: {
		alignItems: "center",
		flex: 1,
		justifyContent: "center",
		paddingHorizontal: Spacing.xxl,
	},
	error: {
		fontSize: FontSize.small,
		lineHeight: 20,
		textAlign: "center",
	},
	retry: {
		alignItems: "center",
		borderRadius: Radius.control,
		flexDirection: "row",
		gap: Spacing.sm,
		marginTop: Spacing.lg,
		minHeight: 44,
		paddingHorizontal: Spacing.xl,
	},
	retryText: { fontSize: FontSize.medium, fontWeight: FontWeight.bold },
	list: { gap: Spacing.md, padding: Spacing.lg },
	listEmpty: { flexGrow: 1 },
	empty: {
		alignItems: "center",
		flex: 1,
		justifyContent: "center",
		paddingHorizontal: Spacing.xxl,
	},
	emptyTitle: {
		fontSize: FontSize.title,
		fontWeight: FontWeight.bold,
		marginTop: Spacing.lg,
	},
	emptyBody: {
		fontSize: FontSize.small,
		marginTop: Spacing.sm,
		textAlign: "center",
	},
	card: {
		alignItems: "center",
		borderRadius: Radius.card,
		flexDirection: "row",
		gap: Spacing.md,
		minHeight: 72,
		padding: Spacing.lg,
	},
	icon: {
		alignItems: "center",
		borderRadius: Radius.md,
		height: 46,
		justifyContent: "center",
		width: 46,
	},
	copy: { flex: 1, minWidth: 0 },
	name: { fontSize: FontSize.body, fontWeight: FontWeight.bold },
	meta: { fontSize: FontSize.caption, marginTop: Spacing.xs },
	pressed: { opacity: 0.62 },
	viewer: { gap: Spacing.md },
	viewerBack: {
		alignItems: "center",
		flexDirection: "row",
		gap: Spacing.sm,
		minHeight: 44,
	},
	viewerBackText: {
		fontSize: FontSize.body,
		fontWeight: FontWeight.semibold,
	},
	viewerHeader: {
		alignItems: "center",
		flexDirection: "row",
		justifyContent: "space-between",
	},
	viewerTitle: { fontSize: FontSize.h3, fontWeight: FontWeight.bold, flex: 1 },
	viewerRow: {
		alignItems: "center",
		flexDirection: "row",
		justifyContent: "space-between",
	},
	viewerLabel: { fontSize: FontSize.caption },
	viewerValue: { fontSize: FontSize.body, fontWeight: FontWeight.semibold },
});

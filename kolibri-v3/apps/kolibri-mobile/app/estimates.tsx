import { useRouter } from "expo-router";
import * as Clipboard from "expo-clipboard";
import * as Linking from "expo-linking";
import {
	ActivityIndicator,
	FlatList,
	KeyboardAvoidingView,
	Platform,
	Pressable,
	ScrollView,
	StyleSheet,
	Text,
	View,
} from "react-native";
import { useCallback, useEffect, useMemo, useState } from "react";

import { NativeScreenShell } from "@/components/shell/native-screen-shell";
import { Icon } from "@/src/components/icons/Icon";
import {
	FontSize,
	FontWeight,
	Layout,
	LetterSpacing,
	LineHeight,
	Radius,
	Spacing,
} from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";
import { actionSheetAsync, confirmAsync } from "@/lib/dialogs";
import { exportAndShare } from "@/lib/mobile/export-file";
import { formatClientError, toClientError } from "@/lib/mobile/observability";
import { PositionCard } from "@/src/components/ui/PositionCard";
import { SectionHeader } from "@/src/components/ui/SectionHeader";
import { SummaryCard } from "@/src/components/ui/SummaryCard";
import { TotalBar } from "@/src/components/ui/TotalBar";
import { Field } from "@/src/components/ui/Field";
import { PillButton } from "@/src/components/ui/PillButton";
import {
	PositionSheet,
	type PositionSheetState,
} from "@/src/components/overlays/PositionSheet";
import { MobileApiError, useMobileSession } from "@/src/auth/mobile-session";
import { constructionEstimateAccess } from "@/src/verticals/construction-estimates/access";
import { ConstructionEstimateClient } from "@/src/verticals/construction-estimates/client";
import {
	isNativeEstimateDraftValid,
	NATIVE_ESTIMATE_PAGE_SIZE,
	type EstimateDocumentSummary,
	type NativeEstimate,
	type NativeEstimateRow,
} from "@/src/verticals/construction-estimates/contracts";
import {
	ESTIMATE_EXPORT_FORMATS,
} from "@/src/verticals/construction-estimates/export";

const formatMoney = (value: string) => {
	if (/^(?:0|[1-9]\d*)(?:\.\d{1,2})?$/.test(value)) {
		const [integer, fraction = ""] = value.split(".");
		const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
		return `${grouped},${fraction.padEnd(2, "0")} ₽`;
	}
	const amount = Number(value);
	return Number.isFinite(amount)
		? new Intl.NumberFormat("ru-RU", {
				currency: "RUB",
				maximumFractionDigits: 2,
				style: "currency",
			}).format(amount)
		: `${value} ₽`;
};

const localLineTotal = (row: NativeEstimateRow) => {
	const total = Number(row.quantity) * Number(row.unitPrice);
	return Number.isFinite(total) ? total : 0;
};

function AccessBoundary({ reason }: { reason: string }) {
	const router = useRouter();
	const { colors } = useTheme();
	return (
		<NativeScreenShell
			onBack={() => router.replace("/app?client=mobile")}
			title="Сметы"
		>
			<View style={styles.boundary}>
				<View
					style={[styles.boundaryIcon, { backgroundColor: colors.surface }]}
				>
					<Icon name="document" color={colors.mutedForeground} size={31} />
				</View>
				<Text style={[styles.boundaryTitle, { color: colors.foreground }]}>
					Мобильный редактор выключен сервером
				</Text>
				<Text style={[styles.boundaryBody, { color: colors.mutedForeground }]}>
					{reason}
				</Text>
				<Text
					accessibilityRole="text"
					style={[styles.boundaryNote, { color: colors.mutedForeground }]}
				>
					Данные и сохранение не подменяются локальным демо.
				</Text>
			</View>
		</NativeScreenShell>
	);
}

function EstimateCard({
	document,
	onPress,
}: {
	document: EstimateDocumentSummary;
	onPress: () => void;
}) {
	const { colors } = useTheme();
	return (
		<Pressable
			accessibilityHint="Открывает сохранённую серверную смету"
			accessibilityLabel={`${document.name}, ${document.rowCount} позиций`}
			accessibilityRole="button"
			disabled={!document.editable}
			onPress={() => {
				haptics.selection();
				onPress();
			}}
			style={({ pressed }) => [
				styles.documentCard,
				{
					backgroundColor: colors.surface,
					opacity: document.editable ? 1 : 0.55,
				},
				pressed && styles.pressed,
			]}
		>
			<View style={styles.documentIcon}>
				<Icon name="document" color={colors.foreground} size={25} />
			</View>
			<View style={styles.documentCopy}>
				<Text
					numberOfLines={2}
					style={[styles.documentName, { color: colors.foreground }]}
				>
					{document.name}
				</Text>
				<Text
					numberOfLines={1}
					style={[styles.documentProject, { color: colors.mutedForeground }]}
				>
					{document.projectName} · v{document.version}
				</Text>
				<Text style={[styles.documentMeta, { color: colors.mutedForeground }]}>
					{document.rowCount} позиций · {formatMoney(document.total)}
				</Text>
			</View>
			<Icon name="chevron-right" color={colors.mutedForeground} size={22} />
		</Pressable>
	);
}

function EstimateCatalog({
	client,
	onOpen,
}: {
	client: ConstructionEstimateClient;
	onOpen: (projectId: string) => void;
}) {
	const { colors } = useTheme();
	const [documents, setDocuments] = useState<
		readonly EstimateDocumentSummary[]
	>([]);
	const [status, setStatus] = useState<"loading" | "ready" | "error">(
		"loading",
	);
	const [message, setMessage] = useState("");

	const load = useCallback(async () => {
		try {
			setDocuments(await client.list());
			setStatus("ready");
		} catch (reason) {
			setMessage(
				reason instanceof Error
					? reason.message
					: "Не удалось загрузить сметы.",
			);
			setStatus("error");
		}
	}, [client]);

	useEffect(() => {
		let active = true;
		void client
			.list()
			.then((next) => {
				if (!active) return;
				setDocuments(next);
				setStatus("ready");
			})
			.catch((reason: unknown) => {
				if (!active) return;
				setMessage(
					reason instanceof Error
						? reason.message
						: "Не удалось загрузить сметы.",
				);
				setStatus("error");
			});
		return () => {
			active = false;
		};
	}, [client]);

	if (status === "loading") {
		return (
			<View accessibilityLabel="Загрузка смет" style={styles.center}>
				<ActivityIndicator color={colors.foreground} />
			</View>
		);
	}

	if (status === "error") {
		return (
			<View style={styles.center}>
				<Text
					accessibilityRole="alert"
					style={[styles.errorText, { color: colors.destructive }]}
				>
					{message}
				</Text>
				<Pressable
					accessibilityRole="button"
					onPress={() => {
						setStatus("loading");
						setMessage("");
						void load();
					}}
					style={[styles.secondaryButton, { backgroundColor: colors.surface }]}
				>
					<Icon name="reload" color={colors.foreground} size={19} />
					<Text
						style={[styles.secondaryButtonText, { color: colors.foreground }]}
					>
						Повторить
					</Text>
				</Pressable>
			</View>
		);
	}

	return (
		<FlatList
			contentContainerStyle={[
				styles.catalog,
				documents.length === 0 && styles.catalogEmpty,
			]}
			data={documents}
			keyExtractor={(document) => document.id}
			ListEmptyComponent={
				<View style={styles.emptyDocuments}>
					<Icon name="document" color={colors.mutedForeground} size={34} />
					<Text style={[styles.emptyTitle, { color: colors.foreground }]}>
						Сохранённых смет пока нет
					</Text>
					<Text style={[styles.emptyBody, { color: colors.mutedForeground }]}>
						Здесь появятся реальные документы V3 после создания в проекте.
					</Text>
				</View>
			}
			renderItem={({ item }) => (
				<EstimateCard document={item} onPress={() => onOpen(item.projectId)} />
			)}
			showsVerticalScrollIndicator={false}
		/>
	);
}

export function EstimateEditor({
	client,
	initial,
	onClose,
}: {
	client: ConstructionEstimateClient;
	initial: NativeEstimate;
	onClose: () => void;
}) {
	const { colors } = useTheme();
	const [estimate, setEstimate] = useState(initial);
	const [title, setTitle] = useState(initial.estimateTitle);
	const [rows, setRows] = useState<readonly NativeEstimateRow[]>(initial.rows);
	const [savedSnapshot, setSavedSnapshot] = useState(() =>
		JSON.stringify({ title: initial.estimateTitle, rows: initial.rows }),
	);
	const [saveState, setSaveState] = useState<
		"idle" | "saving" | "saved" | "error" | "conflict"
	>("idle");
	const [message, setMessage] = useState("");
	const [pageLoading, setPageLoading] = useState(false);
	const [sheet, setSheet] = useState<PositionSheetState | null>(null);

	const snapshot = JSON.stringify({ title, rows });
	const dirty = snapshot !== savedSnapshot;
	const valid = isNativeEstimateDraftValid(title, rows);
	const totalRows = estimate.rowPage?.totalRows ?? rows.length;
	const rowOffset = estimate.rowPage?.offset ?? 0;
	const rowPage = Math.floor(rowOffset / NATIVE_ESTIMATE_PAGE_SIZE);
	const rowPageCount = Math.max(
		1,
		Math.ceil(totalRows / NATIVE_ESTIMATE_PAGE_SIZE),
	);

	const sectionGroups = useMemo(() => {
		const order: string[] = [];
		const map = new Map<string, NativeEstimateRow[]>();
		for (const row of rows) {
			if (!map.has(row.section)) {
				map.set(row.section, []);
				order.push(row.section);
			}
			map.get(row.section)!.push(row);
		}
		return order.map((sectionTitle) => ({
			title: sectionTitle,
			rows: map.get(sectionTitle)!,
		}));
	}, [rows]);

	const sectionTotals = useMemo(
		() =>
			sectionGroups.map((group) => ({
				title: group.title,
				total: group.rows.reduce((sum, row) => sum + localLineTotal(row), 0),
			})),
		[sectionGroups],
	);
	const grandTotal = sectionTotals.reduce((sum, s) => sum + s.total, 0);

	const extraSections = useMemo(() => sectionGroups.map((g) => g.title), [sectionGroups]);
	const extraUnits = useMemo(
		() => [...new Set(rows.map((row) => row.unit))],
		[rows],
	);

	const close = () => {
		if (!dirty) {
			onClose();
			return;
		}
		void confirmAsync(
			"Отменить изменения?",
			"Несохранённые правки этой сметы будут потеряны.",
			{
				acceptLabel: "Отменить правки",
				cancelLabel: "Продолжить редактирование",
				destructive: true,
			},
		).then((confirmed) => {
			if (confirmed) onClose();
		});
	};

	const reload = useCallback(async () => {
		setSaveState("saving");
		setMessage("");
		try {
			const next = await client.open(estimate.projectId, {
				offset: rowOffset,
				limit: NATIVE_ESTIMATE_PAGE_SIZE,
			});
			setEstimate(next);
			setTitle(next.estimateTitle);
			setRows(next.rows);
			setSavedSnapshot(
				JSON.stringify({ title: next.estimateTitle, rows: next.rows }),
			);
			setSaveState("idle");
		} catch (reason) {
			setMessage(
				reason instanceof Error ? reason.message : "Не удалось обновить смету.",
			);
			setSaveState("error");
		}
	}, [client, estimate.projectId, rowOffset]);

	const loadPage = useCallback(
		async (nextPage: number) => {
			if (dirty || pageLoading || saveState === "saving") return;
			setPageLoading(true);
			setMessage("");
			try {
				const next = await client.open(estimate.projectId, {
					offset: Math.max(0, nextPage) * NATIVE_ESTIMATE_PAGE_SIZE,
					limit: NATIVE_ESTIMATE_PAGE_SIZE,
				});
				setEstimate(next);
				setTitle(next.estimateTitle);
				setRows(next.rows);
				setSavedSnapshot(
					JSON.stringify({ title: next.estimateTitle, rows: next.rows }),
				);
				setSaveState("idle");
			} catch (reason) {
				setMessage(
					reason instanceof Error
						? reason.message
						: "Не удалось загрузить страницу сметы.",
				);
				setSaveState("error");
			} finally {
				setPageLoading(false);
			}
		},
		[client, dirty, estimate.projectId, pageLoading, saveState],
	);

	const save = async () => {
		if (!dirty || !valid || saveState === "saving") return;
		setSaveState("saving");
		setMessage("");
		try {
			const next = await client.save(estimate, title, rows);
			setEstimate(next);
			setTitle(next.estimateTitle);
			setRows(next.rows);
			setSavedSnapshot(
				JSON.stringify({ title: next.estimateTitle, rows: next.rows }),
			);
			setSaveState("saved");
			haptics.success();
		} catch (reason) {
			if (
				reason instanceof MobileApiError &&
				reason.code === "estimate_version_conflict"
			) {
				setSaveState("conflict");
				setMessage(reason.message);
			} else {
				setSaveState("error");
				setMessage(
					reason instanceof Error ? reason.message : "Не удалось сохранить.",
				);
			}
			haptics.error();
		}
	};

	const exportEstimate = () => {
		void actionSheetAsync(
			"Экспорт сметы",
			[
				...ESTIMATE_EXPORT_FORMATS.map((format) => ({
					text: format.toUpperCase(),
					onPress: () => {
						void client
							.export(estimate.projectId, format)
							.then(exportAndShare)
							.catch((reason: unknown) => {
								setSaveState("error");
								setMessage(
									formatClientError(
										toClientError(
											reason,
											"Не удалось экспортировать смету.",
										),
									),
								);
								haptics.error();
							});
					},
				})),
				{
					text: "Скопировать ссылку на смету",
					onPress: () => {
						const url = Linking.createURL(
							`/estimate/${encodeURIComponent(estimate.projectId)}?client=mobile`,
						);
						void Clipboard.setStringAsync(url).then(() => {
							setSaveState("saved");
							setMessage("Ссылка скопирована в буфер обмена.");
							haptics.success();
						});
					},
				},
			],
		);
	};

	const handleSavePosition = (row: NativeEstimateRow) => {
		setRows((current) =>
			current.some((existing) => existing.id === row.id)
				? current.map((existing) => (existing.id === row.id ? row : existing))
				: [...current, row],
		);
		setSaveState("idle");
		setSheet({ mode: "view", row });
	};

	const handleDeletePosition = (id: string) => {
		setRows((current) => current.filter((row) => row.id !== id));
		setSaveState("idle");
		setSheet(null);
	};

	return (
		<NativeScreenShell
			onBack={close}
			subtitle={`Версия ${estimate.version}`}
			title="Сметы"
		>
			<KeyboardAvoidingView
				behavior={Platform.OS === "ios" ? "padding" : undefined}
				style={styles.flex}
			>
				<ScrollView
					contentContainerStyle={styles.editorContent}
					keyboardDismissMode="interactive"
					keyboardShouldPersistTaps="handled"
					showsVerticalScrollIndicator={false}
				>
					<Field
						label="Название сметы"
						maxLength={240}
						onChangeText={(value) => {
							setTitle(value);
							setSaveState("idle");
						}}
						value={title}
					/>
					<SummaryCard sections={sectionTotals} total={grandTotal} />
					{rowPageCount > 1 ? (
						<View style={styles.pagination}>
							<Pressable
								accessibilityRole="button"
								disabled={rowPage === 0 || dirty || pageLoading}
								onPress={() => void loadPage(Math.max(0, rowPage - 1))}
								style={styles.pageButton}
							>
								<Text style={[styles.pageButtonText, { color: colors.foreground }]}>
									Назад
								</Text>
							</Pressable>
							<Text style={[styles.pageLabel, { color: colors.mutedForeground }]}>
								{rowOffset + 1}–{Math.min(rowOffset + rows.length, totalRows)} из {totalRows}
							</Text>
							<Pressable
								accessibilityRole="button"
								disabled={rowPage >= rowPageCount - 1 || dirty || pageLoading}
								onPress={() =>
									void loadPage(Math.min(rowPageCount - 1, rowPage + 1))
								}
								style={styles.pageButton}
							>
								<Text style={[styles.pageButtonText, { color: colors.foreground }]}>
									Далее
								</Text>
							</Pressable>
						</View>
					) : null}
					{sectionGroups.map((group) => (
						<View key={group.title} style={styles.sectionBlock}>
							<SectionHeader title={group.title} />
							<View style={styles.sectionCards}>
								{group.rows.map((row) => (
									<PositionCard
										key={row.id}
										name={row.description}
										onPress={() => setSheet({ mode: "view", row })}
										price={Number(row.unitPrice) || 0}
										qty={Number(row.quantity) || 0}
										unit={row.unit}
									/>
								))}
							</View>
						</View>
					))}
				</ScrollView>
			</KeyboardAvoidingView>
			<View
				style={[
					styles.bottomBar,
					{ backgroundColor: colors.background, borderTopColor: colors.muted },
				]}
			>
				<View style={styles.saveMessage}>
					<Text
						accessibilityLiveRegion="polite"
						numberOfLines={2}
						style={[
							styles.saveMessageText,
							{
								color:
									saveState === "error" || saveState === "conflict"
										? colors.destructive
										: colors.mutedForeground,
							},
						]}
					>
						{saveState === "saving"
							? "Сохраняю…"
							: saveState === "saved"
								? "Сохранено на сервере"
								: message ||
									(dirty ? "Есть несохранённые изменения" : "Актуально")}
					</Text>
					{saveState === "conflict" ? (
						<Pressable
							accessibilityRole="button"
							onPress={() => void reload()}
							style={styles.reloadLink}
						>
							<Text
								style={[
									styles.reloadLinkText,
									{ color: colors.foreground },
								]}
							>
								Обновить
							</Text>
						</Pressable>
					) : null}
				</View>
				<View style={styles.bottomButtons}>
					<PillButton
						disabled={!dirty || !valid || saveState === "saving"}
						filled
						icon="save"
						onPress={() => void save()}
						title="Сохранить"
					/>
					<PillButton
						disabled={dirty || saveState === "saving" || totalRows === 0}
						icon="share"
						onPress={exportEstimate}
						title="Поделиться"
					/>
				</View>
				<TotalBar
					onAdd={() => setSheet({ mode: "edit", row: null })}
					total={grandTotal}
				/>
			</View>
			<PositionSheet
				extraSections={extraSections}
				extraUnits={extraUnits}
				key={
					sheet
						? sheet.row?.id ?? "new"
						: "closed"
				}
				onClose={() => setSheet(null)}
				onDelete={handleDeletePosition}
				onSave={handleSavePosition}
				onSwitchToEdit={() =>
					setSheet((current) =>
						current ? { ...current, mode: "edit" } : current,
					)
				}
				state={sheet}
			/>
		</NativeScreenShell>
	);
}

export default function EstimatesScreen() {
	const router = useRouter();
	const session = useMobileSession();
	const { colors } = useTheme();
	const access = constructionEstimateAccess(session.user);
	const client = useMemo(
		() => new ConstructionEstimateClient(session.authorizedFetch),
		[session.authorizedFetch],
	);
	const [selected, setSelected] = useState<NativeEstimate | null>(null);
	const [opening, setOpening] = useState(false);
	const [error, setError] = useState("");

	const open = useCallback(async (projectId: string) => {
		setOpening(true);
		setError("");
		try {
			setSelected(await client.open(projectId));
		} catch (reason) {
			setError(
				reason instanceof Error ? reason.message : "Не удалось открыть смету.",
			);
			haptics.error();
		} finally {
			setOpening(false);
		}
	}, [client]);

	if (!access.enabled) return <AccessBoundary reason={access.reason} />;

	if (selected) {
		return (
			<EstimateEditor
				client={client}
				initial={selected}
				onClose={() => setSelected(null)}
			/>
		);
	}

	return (
		<NativeScreenShell
			onBack={() => router.replace("/app?client=mobile")}
			title="Сметы"
		>
			{error ? (
				<Text
					accessibilityRole="alert"
					style={[styles.inlineError, { color: colors.destructive }]}
				>
					{error}
				</Text>
			) : null}
			{opening ? (
				<View accessibilityLabel="Открытие сметы" style={styles.center}>
					<ActivityIndicator color={colors.foreground} />
				</View>
			) : (
				<EstimateCatalog client={client} onOpen={(id) => void open(id)} />
			)}
		</NativeScreenShell>
	);
}

const styles = StyleSheet.create({
	safe: { flex: 1 },
	flex: { flex: 1 },
	header: {
		alignItems: "center",
		flexDirection: "row",
		height: 76,
		paddingHorizontal: Spacing.lg,
	},
	headerCopy: { alignItems: "center", flex: 1, paddingHorizontal: Spacing.sm },
	headerTitle: {
		fontSize: FontSize.h1,
		fontWeight: FontWeight.bold,
		letterSpacing: LetterSpacing.tight,
	},
	headerSubtitle: { fontSize: FontSize.caption, marginTop: Spacing.xs },
	headerBalance: { height: 48, width: 48 },
	boundary: {
		alignItems: "center",
		flex: 1,
		justifyContent: "center",
		paddingHorizontal: Spacing.xxxl,
		paddingBottom: Spacing.xxxl * 2 + Spacing.sm,
	},
	boundaryIcon: {
		alignItems: "center",
		borderRadius: Radius.badge,
		height: 68,
		justifyContent: "center",
		width: 68,
	},
	boundaryTitle: {
		fontSize: FontSize.h3,
		fontWeight: FontWeight.bold,
		letterSpacing: LetterSpacing.medium,
		marginTop: Layout.composerInset,
		textAlign: "center",
	},
	boundaryBody: {
		fontSize: FontSize.medium,
		lineHeight: LineHeight.base,
		marginTop: Spacing.md,
		textAlign: "center",
	},
	boundaryNote: {
		fontSize: FontSize.caption,
		lineHeight: LineHeight.footnote,
		marginTop: Spacing.md,
		textAlign: "center",
	},
	center: {
		alignItems: "center",
		flex: 1,
		justifyContent: "center",
		paddingHorizontal: Spacing.xxl,
	},
	catalog: { gap: Spacing.md, padding: Spacing.lg, paddingBottom: Spacing.xxl },
	catalogEmpty: { flexGrow: 1 },
	documentCard: {
		alignItems: "center",
		borderRadius: Radius.card,
		flexDirection: "row",
		minHeight: 102,
		paddingHorizontal: Spacing.lg,
		paddingVertical: Spacing.lg,
	},
	documentIcon: {
		alignItems: "center",
		height: 45,
		justifyContent: "center",
		width: 45,
	},
	documentCopy: {
		flex: 1,
		marginLeft: Spacing.sm,
		marginRight: Spacing.sm,
	},
	documentName: {
		fontSize: FontSize.text,
		fontWeight: FontWeight.bold,
		lineHeight: LineHeight.base,
	},
	documentProject: { fontSize: FontSize.footnote, marginTop: Spacing.xs },
	documentMeta: { fontSize: FontSize.caption, marginTop: Spacing.xs },
	emptyDocuments: {
		alignItems: "center",
		flex: 1,
		justifyContent: "center",
		paddingBottom: Spacing.xxxl * 2 + Spacing.sm,
		paddingHorizontal: Spacing.xxl,
	},
	emptyTitle: {
		fontSize: FontSize.title,
		fontWeight: FontWeight.bold,
		marginTop: Spacing.lg,
	},
	emptyBody: {
		fontSize: FontSize.small,
		lineHeight: LineHeight.normal,
		marginTop: Spacing.sm,
		textAlign: "center",
	},
	errorText: {
		fontSize: FontSize.small,
		lineHeight: LineHeight.normal,
		textAlign: "center",
	},
	secondaryButton: {
		alignItems: "center",
		borderRadius: Radius.control,
		flexDirection: "row",
		gap: Spacing.sm,
		marginTop: Spacing.lg,
		minHeight: 44,
		paddingHorizontal: Layout.composerInset,
	},
	secondaryButtonText: {
		fontSize: FontSize.medium,
		fontWeight: FontWeight.bold,
	},
	inlineError: {
		fontSize: FontSize.footnote,
		lineHeight: LineHeight.compact,
		paddingHorizontal: Layout.composerInset,
		paddingVertical: Spacing.sm,
		textAlign: "center",
	},
	editorContent: {
		gap: Spacing.lg,
		padding: Spacing.lg,
		paddingBottom: Spacing.xl,
	},
	pagination: {
		alignItems: "center",
		flexDirection: "row",
		justifyContent: "space-between",
		minHeight: 44,
	},
	pageButton: {
		justifyContent: "center",
		minHeight: 44,
		paddingHorizontal: Spacing.sm,
	},
	pageButtonText: { fontSize: FontSize.medium, fontWeight: FontWeight.semibold },
	pageLabel: { flex: 1, fontSize: FontSize.caption, textAlign: "center" },
	sectionBlock: { gap: Spacing.md },
	sectionCards: { gap: Spacing.md },
	bottomBar: {
		borderTopWidth: StyleSheet.hairlineWidth,
		gap: Spacing.md,
		paddingHorizontal: Spacing.lg,
		paddingTop: Spacing.md,
	},
	saveMessage: { minHeight: 30 },
	saveMessageText: { fontSize: FontSize.caption, lineHeight: LineHeight.caption },
	reloadLink: {
		marginTop: Spacing.xs,
		minHeight: 25,
		justifyContent: "center",
	},
	reloadLinkText: { fontSize: FontSize.footnote, fontWeight: FontWeight.bold },
	bottomButtons: { alignItems: "stretch" },
	pressed: { opacity: 0.58 },
});

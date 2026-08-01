"use client";

import {
	CheckCircle2Icon,
	ChevronDownIcon,
	DownloadIcon,
	LoaderCircleIcon,
	PlusIcon,
	RefreshCwIcon,
	Trash2Icon,
} from "lucide-react";
import {
	Fragment,
	useCallback,
	useEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import { Button } from "@/components/ui/button";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuLabel,
	DropdownMenuSeparator,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { withCsrfHeader } from "@/lib/csrf";
import { kolibriGenerativeUIComponentSchemas } from "@/lib/generative-ui/schema";
import {
	diffEstimateDrafts,
	type EstimateDraftConflictDiff,
	type EstimateDraftSnapshot,
	parseEstimateVersionConflict,
} from "@/lib/estimate-version-conflict";
import { cn } from "@/lib/utils";
import {
	announceDocumentsChanged,
} from "@/lib/workspace-events";
import { toAmount, formatMoney, readResponseError, emptyRow } from "./helpers";
import { loadEstimateDocument } from "./estimate-document-common";

import type {
	EstimateWidgetProps,
	EditableEstimateRow,
	EstimateExportFormat,
	PriceEvidence,
	EnginePriceProvenance,
} from "./types";

type EstimateRow = EstimateWidgetProps["rows"][number];
type EstimateEditorWidgetProps = EstimateWidgetProps & {
	presentation?: "canvas" | "inline";
};
type EstimateConflictState = {
	currentVersion: number;
	expectedVersion: number;
	authoritative: EstimateWidgetProps | null;
	diff: EstimateDraftConflictDiff | null;
};

const editableRowsFromEstimate = (estimate: EstimateWidgetProps) =>
	estimate.rows.map(({ lineTotal: _lineTotal, ...row }) => row);

const draftSnapshotFromEstimate = (
	estimate: EstimateWidgetProps,
): EstimateDraftSnapshot => ({
	title: estimate.estimateTitle,
	rows: editableRowsFromEstimate(estimate),
});

function EstimateConflictItems({
	items,
	label,
}: {
	items: readonly string[];
	label: string;
}) {
	if (items.length === 0) return null;
	const visibleItems = items.slice(0, 4);
	return (
		<div className="min-w-0">
			<p className="text-xs font-semibold">{label}</p>
			<ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
				{visibleItems.map((item) => (
					<li key={item} className="truncate">
						{item}
					</li>
				))}
				{items.length > visibleItems.length ? (
					<li>Ещё изменений: {items.length - visibleItems.length}</li>
				) : null}
			</ul>
		</div>
	);
};

const isoDateAfter = (days: number) => {
	const value = new Date();
	value.setDate(value.getDate() + days);
	return value.toISOString().slice(0, 10);
};

const priceSourceLabel = (evidence: PriceEvidence) => {
	if (evidence.status === "stale") return "Цена устарела";
	if (evidence.sourceType === "fgis_cs") return "ФГИС ЦС";
	if (evidence.bindingStatus === "user_attested_binding") {
		return "Предложение поставщика";
	}
	return "Цена поставщика";
};

const enginePriceSourceLabel = (provenance: EnginePriceProvenance) => {
	if (!provenance.verified) return "AI‑кандидат · не проверено";
	if (provenance.sourceType === "regional_catalog") {
		return "Региональный каталог";
	}
	if (provenance.sourceType === "supplier_offer") {
		return "Предложение поставщика";
	}
	if (provenance.sourceType === "organization_price") {
		return "Цена организации";
	}
	return "Цена пользователя";
};

const engineVatLabel = (vatMode: EnginePriceProvenance["vatMode"]) => {
	if (vatMode === "included") return "НДС включён";
	if (vatMode === "excluded") return "без НДС";
	if (vatMode === "not_applicable") return "без НДС";
	return "НДС не указан";
};

const estimateKindLabel = (kind: EditableEstimateRow["kind"]) => {
	if (kind === "work") return "работа";
	if (kind === "material") return "материал";
	if (kind === "equipment") return "оборудование";
	return "услуга";
};

function EstimateRowEvidence({
	row,
	className,
}: {
	row: EditableEstimateRow;
	className?: string;
}) {
	return (
		<details className={className}>
			<summary className="min-h-11 cursor-pointer select-none py-3 font-medium text-foreground">
				Основание количества и цены
			</summary>
			<div className="space-y-1 pb-2 leading-5 text-muted-foreground">
				<p>Количество: {row.quantityBasis}</p>
				<p>Цена: {row.priceBasis}</p>
				{row.priceEvidence ? (
					<>
						<p>
							Регион: {row.priceEvidence.region}
							{row.priceEvidence.period ? ` · ${row.priceEvidence.period}` : ""}
						</p>
						<p>
							{row.priceEvidence.freshnessBasis === "supplier_valid_until"
								? "Действует до"
								: "Проверить актуальность после"}{" "}
							{row.priceEvidence.freshUntil} ·{" "}
							{row.priceEvidence.taxStatus === "included"
								? "НДС включён"
								: row.priceEvidence.taxStatus === "excluded"
									? "без НДС"
									: "НДС не указан"}
						</p>
						{row.priceEvidence.landedCostStatus === "not_calculated" ? (
							<p>Справочная цена · доставка и складирование не рассчитаны</p>
						) : (
							<p>
								Цена с доставкой:{" "}
								{formatMoney(Number(row.priceEvidence.landedUnitPrice))}
							</p>
						)}
						<a
							className="inline-flex text-foreground underline underline-offset-2"
							href={row.priceEvidence.sourceUrl}
							target="_blank"
							rel="noreferrer"
						>
							Источник · {row.priceEvidence.sourceReference}
						</a>
						<p title={row.priceEvidence.snapshotHash}>
							Снимок: {row.priceEvidence.snapshotHash.slice(0, 18)}…
						</p>
					</>
				) : row.enginePriceProvenance ? (
					<>
						<p
							className={
								row.enginePriceProvenance.verified
									? "text-emerald-700 dark:text-emerald-400"
									: "text-amber-700 dark:text-amber-400"
							}
						>
							{enginePriceSourceLabel(row.enginePriceProvenance)}
						</p>
						<p>
							{row.enginePriceProvenance.label} ·{" "}
							{row.enginePriceProvenance.reference}
						</p>
						<p>
							Регион: {row.enginePriceProvenance.region} · на{" "}
							{row.enginePriceProvenance.observedAt.slice(0, 10)}
						</p>
						<p>
							{engineVatLabel(row.enginePriceProvenance.vatMode)} · уверенность{" "}
							{Math.round(Number(row.enginePriceProvenance.confidence) * 100)}%
						</p>
						{row.enginePriceProvenance.validUntil ? (
							<p>
								Действует до {row.enginePriceProvenance.validUntil.slice(0, 10)}
							</p>
						) : null}
						{row.enginePriceProvenance.sourceUrl.startsWith("https://") ? (
							<a
								className="inline-flex text-foreground underline underline-offset-2"
								href={row.enginePriceProvenance.sourceUrl}
								target="_blank"
								rel="noreferrer"
							>
								Открыть источник
							</a>
						) : (
							<p>Источник сохранён в текущем расчёте</p>
						)}
					</>
				) : (
					<p className="text-amber-700 dark:text-amber-400">
						Цена введена без подтверждённого источника.
					</p>
				)}
			</div>
		</details>
	);
}


function SupplierOfferForm({
	projectId,
	row,
	version,
	onApplied,
}: {
	projectId: string;
	row: EditableEstimateRow;
	version: number;
	onApplied: (estimate: EstimateWidgetProps, message: string) => void;
}) {
	const [supplierName, setSupplierName] = useState("");
	const [sourceUrl, setSourceUrl] = useState("");
	const [quoteReference, setQuoteReference] = useState("");
	const [observedOn, setObservedOn] = useState(() => isoDateAfter(0));
	const [validUntil, setValidUntil] = useState(() => isoDateAfter(30));
	const [unitPrice, setUnitPrice] = useState(row.unitPrice);
	const [deliveryPerUnit, setDeliveryPerUnit] = useState("0.00");
	const [vatStatus, setVatStatus] = useState<
		"included" | "excluded" | "unknown"
	>("unknown");
	const [offerKind, setOfferKind] = useState<"indicative" | "binding">(
		"indicative",
	);
	const [submitting, setSubmitting] = useState(false);
	const [error, setError] = useState("");

	const submit = async () => {
		if (
			!supplierName.trim() ||
			!sourceUrl.trim() ||
			!quoteReference.trim() ||
			!observedOn ||
			!/^(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$/.test(unitPrice) ||
			!/^(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$/.test(deliveryPerUnit)
		) {
			setError("Заполните поставщика, ссылку, номер предложения и цену.");
			return;
		}
		setSubmitting(true);
		setError("");
		try {
			const response = await fetch(
				`/api/v3/projects/${encodeURIComponent(projectId)}/estimate/prices/supplier-offers`,
				{
					method: "POST",
					headers: withCsrfHeader({
						Accept: "application/json",
						"Content-Type": "application/json",
						"Idempotency-Key": `supplier-offer-${globalThis.crypto.randomUUID()}`,
					}),
					body: JSON.stringify({
						version,
						rowId: row.id,
						supplierName: supplierName.trim(),
						sourceUrl: sourceUrl.trim(),
						quoteReference: quoteReference.trim(),
						observedOn,
						validUntil: validUntil || null,
						unitPrice,
						deliveryPerUnit,
						vatIncluded:
							vatStatus === "included"
								? true
								: vatStatus === "excluded"
									? false
									: null,
						offerKind,
						availability: "unknown",
						leadTimeDays: null,
					}),
					credentials: "same-origin",
					cache: "no-store",
				},
			);
			if (!response.ok) {
				throw new Error(await readResponseError(response));
			}
			const value: unknown = await response.json();
			const record =
				typeof value === "object" && value !== null
					? (value as Record<string, unknown>)
					: null;
			const parsed =
				kolibriGenerativeUIComponentSchemas.EstimateEditor.safeParse(
					record?.estimate,
				);
			if (!parsed.success) {
				throw new Error("Сервер вернул смету неизвестного формата.");
			}
			onApplied(
				parsed.data,
				typeof record?.message === "string"
					? record.message
					: "Предложение поставщика прикреплено.",
			);
		} catch (caught) {
			setError(
				caught instanceof Error
					? caught.message
					: "Не удалось прикрепить предложение.",
			);
		} finally {
			setSubmitting(false);
		}
	};

	return (
		<div className="mt-2 rounded-lg border border-border bg-background p-3">
			<p className="text-xs font-medium text-foreground">
				Предложение для «{row.description}»
			</p>
			<div className="mt-2 grid gap-2 sm:grid-cols-2">
				<Input
					aria-label="Поставщик"
					placeholder="Поставщик"
					value={supplierName}
					maxLength={240}
					onChange={(event) => setSupplierName(event.target.value)}
				/>
				<Input
					aria-label="Номер предложения"
					placeholder="КП-2026/41"
					value={quoteReference}
					maxLength={160}
					onChange={(event) => setQuoteReference(event.target.value)}
				/>
				<Input
					aria-label="Ссылка на предложение поставщика"
					type="url"
					placeholder="https://supplier.ru/quote/..."
					value={sourceUrl}
					maxLength={1_000}
					onChange={(event) => setSourceUrl(event.target.value)}
				/>
				<select
					aria-label="Статус предложения"
					className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
					value={offerKind}
					onChange={(event) =>
						setOfferKind(event.target.value as "indicative" | "binding")
					}
				>
					<option value="indicative">Ориентировочное</option>
					<option value="binding">
						Заявлено как действующее · не проверено Kolibri
					</option>
				</select>
				<label className="text-[11px] text-muted-foreground">
					Дата предложения
					<Input
						type="date"
						value={observedOn}
						max={new Date().toISOString().slice(0, 10)}
						onChange={(event) => setObservedOn(event.target.value)}
					/>
				</label>
				<label className="text-[11px] text-muted-foreground">
					Действует до
					<Input
						type="date"
						value={validUntil}
						required={offerKind === "binding"}
						onChange={(event) => setValidUntil(event.target.value)}
					/>
				</label>
				<label className="text-[11px] text-muted-foreground">
					Цена за {row.unit}
					<Input
						inputMode="decimal"
						value={unitPrice}
						onChange={(event) => setUnitPrice(event.target.value)}
					/>
				</label>
				<label className="text-[11px] text-muted-foreground">
					Доставка за {row.unit}
					<Input
						inputMode="decimal"
						value={deliveryPerUnit}
						onChange={(event) => setDeliveryPerUnit(event.target.value)}
					/>
				</label>
				<select
					aria-label="НДС в предложении"
					className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
					value={vatStatus}
					onChange={(event) =>
						setVatStatus(
							event.target.value as "included" | "excluded" | "unknown",
						)
					}
				>
					<option value="unknown">НДС не указан</option>
					<option value="included">НДС включён</option>
					<option value="excluded">Без НДС</option>
				</select>
			</div>
			<div className="mt-3 flex flex-wrap items-center gap-2">
				<Button
					type="button"
					size="sm"
					disabled={submitting}
					onClick={() => void submit()}
				>
					{submitting ? (
						<LoaderCircleIcon className="size-4 animate-spin" />
					) : (
						<CheckCircle2Icon className="size-4" />
					)}
					Прикрепить цену
				</Button>
				{error ? (
					<span className="text-xs text-destructive" role="alert">
						{error}
					</span>
				) : (
					<span className="text-xs text-muted-foreground">
						Реквизиты предложения и их hash сохранятся в истории.
					</span>
				)}
			</div>
		</div>
	);
}

export function EstimateEditorWidget({
	presentation = "canvas",
	...initial
}: EstimateEditorWidgetProps) {
	const hasLocalEdits = useRef(false);
	const savingRef = useRef(false);
	const latestSnapshotRef = useRef("");
	const [version, setVersion] = useState(initial.version);
	const [title, setTitle] = useState(initial.estimateTitle);
	const [region, setRegion] = useState(initial.estimateRegion);
	const [assumptions, setAssumptions] = useState(initial.assumptions);
	const [pricing, setPricing] = useState(initial.pricing);
	const [rows, setRows] = useState<EditableEstimateRow[]>(() =>
		initial.rows.map(({ lineTotal: _lineTotal, ...row }) => row),
	);
	const [savedSnapshot, setSavedSnapshot] = useState(() =>
		JSON.stringify({ title: initial.estimateTitle, rows }),
	);
	const [saveState, setSaveState] = useState<
		"idle" | "saving" | "saved" | "error" | "conflict"
	>("idle");
	const [saveMessage, setSaveMessage] = useState("");
	const [saveRetryAttempt, setSaveRetryAttempt] = useState(0);
	const [saveErrorRetryable, setSaveErrorRetryable] = useState(false);
	const [versionConflict, setVersionConflict] =
		useState<EstimateConflictState | null>(null);
	const [actionMessage, setActionMessage] = useState("");
	const [priceRefreshState, setPriceRefreshState] = useState<
		"idle" | "checking" | "error"
	>("idle");
	const [offerRowId, setOfferRowId] = useState<string | null>(null);

	const currentSnapshot = JSON.stringify({ title, rows });
	latestSnapshotRef.current = currentSnapshot;
	const dirty = currentSnapshot !== savedSnapshot;

	useEffect(() => {
		if (
			initial.documentId === "" ||
			initial.version <= version ||
			versionConflict?.currentVersion === initial.version
		) {
			return;
		}

		const nextRows = editableRowsFromEstimate(initial);
		const nextSnapshot = JSON.stringify({
			title: initial.estimateTitle,
			rows: nextRows,
		});
		if (dirty || hasLocalEdits.current || savingRef.current) {
			const baseline = JSON.parse(savedSnapshot) as EstimateDraftSnapshot;
			const local = JSON.parse(
				latestSnapshotRef.current,
			) as EstimateDraftSnapshot;
			setVersionConflict({
				expectedVersion: version,
				currentVersion: initial.version,
				authoritative: initial,
				diff: diffEstimateDrafts(
					baseline,
					local,
					draftSnapshotFromEstimate(initial),
				),
			});
			setSaveMessage(
				`Серверная версия ${initial.version} загружена для сравнения. Локальный черновик не изменён.`,
			);
			setSaveErrorRetryable(false);
			setSaveState("conflict");
			return;
		}

		setVersion(initial.version);
		setTitle(initial.estimateTitle);
		setRegion(initial.estimateRegion);
		setAssumptions(initial.assumptions);
		setPricing(initial.pricing);
		setRows(nextRows);
		setSavedSnapshot(nextSnapshot);
		hasLocalEdits.current = false;
		setVersionConflict(null);
		setSaveMessage("");
		setSaveRetryAttempt(0);
		setSaveErrorRetryable(false);
		setSaveState("saved");
	}, [
		dirty,
		initial,
		savedSnapshot,
		version,
		versionConflict?.currentVersion,
	]);
	const valid =
		title.trim().length > 0 &&
		rows.every(
			(row) =>
				row.description.trim().length > 0 &&
				/^(?:0|[1-9]\d{0,11})(?:\.\d{1,6})?$/.test(row.quantity) &&
				/^(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$/.test(row.unitPrice),
		);
	const total = useMemo(
		() =>
			rows.reduce((sum, row) => sum + toAmount(row.quantity, row.unitPrice), 0),
		[rows],
	);
	const materialRowCount = rows.filter((row) => row.kind === "material").length;
	const pricingLabel =
		pricing.status === "sourced"
			? `С источником ${pricing.sourcedRows} из ${pricing.totalRows}`
			: pricing.status === "partially_sourced"
				? `С источником ${pricing.sourcedRows} из ${pricing.totalRows}`
				: pricing.status === "stale"
					? `Устарело цен: ${pricing.staleRows}`
					: "Источники цен не добавлены";

	useEffect(() => {
		setSaveRetryAttempt(0);
		setSaveErrorRetryable(false);
		setSaveState((current) => (current === "error" ? "idle" : current));
	}, [currentSnapshot]);

	const updateRow = (
		id: string,
		field: "description" | "unit" | "quantity" | "unitPrice",
		value: string,
	) => {
		hasLocalEdits.current = true;
		setRows((current) =>
			current.map((row) => {
				if (row.id !== id) return row;
				const invalidatesPrice =
					field === "description" || field === "unit" || field === "unitPrice";
				return {
					...row,
					[field]: value,
					...(invalidatesPrice
						? {
								priceBasis: "Введено пользователем",
								priceEvidence: null,
							}
						: null),
				};
			}),
		);
		setSaveState((current) => (current === "conflict" ? current : "idle"));
	};

	const downloadEstimate = (format: EstimateExportFormat) => {
		const anchor = document.createElement("a");
		anchor.href = `/api/v3/projects/${encodeURIComponent(initial.projectId)}/estimate/export/${format}`;
		anchor.download = "";
		if (format === "zip") {
			anchor.target = "_blank";
			anchor.rel = "noopener noreferrer";
		}
		document.body.append(anchor);
		anchor.click();
		anchor.remove();
		setActionMessage(
			`${
				format === "xlsx"
					? "Excel"
					: format === "docx"
						? "Word"
						: format === "zip"
							? "Пакет ZIP"
							: format.toUpperCase()
			} скачивается`,
		);
	};

	const save = useCallback(async () => {
		if (!dirty || !valid || savingRef.current || versionConflict) return;
		const snapshotAtStart = currentSnapshot;
		const versionAtStart = version;
		const titleAtStart = title.trim();
		const rowsAtStart = rows.map(
			({
				priceEvidence: _priceEvidence,
				enginePriceProvenance: _enginePriceProvenance,
				...row
			}) => ({
				...row,
				description: row.description.trim(),
				unit: row.unit.trim(),
			}),
		);
		savingRef.current = true;
		setSaveState("saving");
		setSaveMessage("");
		try {
			const headers = withCsrfHeader({
				Accept: "application/json",
				"Content-Type": "application/json",
			});
			const response = await fetch(
				`/api/v3/projects/${encodeURIComponent(initial.projectId)}/estimate`,
				{
					method: "PATCH",
					headers,
					body: JSON.stringify({
						version: versionAtStart,
						title: titleAtStart,
						currency: initial.currency,
						rows: rowsAtStart,
					}),
					credentials: "same-origin",
					cache: "no-store",
				},
			);
			if (!response.ok) {
				let errorPayload: unknown = null;
				try {
					errorPayload = await response.clone().json();
				} catch {
					// The bounded fallback below remains available for non-JSON errors.
				}
				const conflict = parseEstimateVersionConflict(
					response.status,
					errorPayload,
				);
				if (conflict) {
					let authoritative: EstimateWidgetProps | null = null;
					try {
						authoritative = await loadEstimateDocument({
							documentId: initial.documentId,
							minimumVersion: versionAtStart,
							projectId: initial.projectId,
						});
					} catch {
						// Keep the local draft even when the current server copy cannot
						// be loaded yet. The user can retry the comparison explicitly.
					}
					const baseline = JSON.parse(savedSnapshot) as EstimateDraftSnapshot;
					const local = JSON.parse(
						latestSnapshotRef.current,
					) as EstimateDraftSnapshot;
					const currentVersion =
						authoritative?.version ?? conflict.currentVersion;
					setVersionConflict({
						...conflict,
						currentVersion,
						authoritative,
						diff: authoritative
							? diffEstimateDrafts(
									baseline,
									local,
									draftSnapshotFromEstimate(authoritative),
								)
							: null,
					});
					setSaveMessage(
						authoritative
							? `Серверная версия ${currentVersion} загружена для сравнения. Локальный черновик не изменён.`
							: `На сервере уже версия ${currentVersion}. Локальный черновик не изменён; повторите загрузку сравнения.`,
					);
					setSaveErrorRetryable(false);
					setSaveState("conflict");
					return;
				}
				setSaveMessage(await readResponseError(response));
				setSaveErrorRetryable(
					response.status === 408 ||
						response.status === 429 ||
						response.status >= 500,
				);
				setSaveRetryAttempt((current) => current + 1);
				setSaveState("error");
				return;
			}
			const value = (await response.json()) as unknown;
			const parsed =
				kolibriGenerativeUIComponentSchemas.EstimateEditor.safeParse(value);
			if (!parsed.success) {
				setSaveMessage("Сервер вернул смету неизвестного формата.");
				setSaveErrorRetryable(false);
				setSaveState("error");
				return;
			}
			const nextRows = parsed.data.rows.map(
				({ lineTotal: _lineTotal, ...row }) => row,
			);
			const nextSavedSnapshot = JSON.stringify({
				title: parsed.data.estimateTitle,
				rows: nextRows,
			});
			const noNewEdits = latestSnapshotRef.current === snapshotAtStart;
			setVersion(parsed.data.version);
			setRegion(parsed.data.estimateRegion);
			setAssumptions(parsed.data.assumptions);
			setPricing(parsed.data.pricing);
			setSavedSnapshot(nextSavedSnapshot);
			if (noNewEdits) {
				setTitle(parsed.data.estimateTitle);
				setRows(nextRows);
				hasLocalEdits.current = false;
			}
			announceDocumentsChanged();
			setSaveRetryAttempt(0);
			setSaveErrorRetryable(false);
			setSaveState(noNewEdits ? "saved" : "idle");
		} catch {
			setSaveMessage("Нет связи с сервером. Изменения остались в редакторе.");
			setSaveErrorRetryable(true);
			setSaveRetryAttempt((current) => current + 1);
			setSaveState("error");
		} finally {
			savingRef.current = false;
		}
	}, [
		currentSnapshot,
		dirty,
		initial.currency,
		initial.projectId,
		rows,
		savedSnapshot,
		title,
		valid,
		version,
		versionConflict,
	]);

	const refreshVersionConflict = useCallback(async () => {
		if (!versionConflict) return;
		setSaveMessage("Загружаю текущую серверную версию для сравнения…");
		try {
			const authoritative = await loadEstimateDocument({
				documentId: initial.documentId,
				minimumVersion: version,
				projectId: initial.projectId,
			});
			const baseline = JSON.parse(savedSnapshot) as EstimateDraftSnapshot;
			const local = JSON.parse(
				latestSnapshotRef.current,
			) as EstimateDraftSnapshot;
			setVersionConflict((current) =>
				current
					? {
							...current,
							authoritative,
							currentVersion: authoritative.version,
							diff: diffEstimateDrafts(
								baseline,
								local,
								draftSnapshotFromEstimate(authoritative),
							),
						}
					: null,
			);
			setSaveMessage(
				`Серверная версия ${authoritative.version} загружена. Локальный черновик не изменён.`,
			);
		} catch {
			setSaveMessage(
				"Не удалось загрузить серверную версию. Локальный черновик остаётся в редакторе.",
			);
		}
	}, [
		initial.documentId,
		initial.projectId,
		savedSnapshot,
		version,
		versionConflict,
	]);

	const useAuthoritativeVersion = useCallback(() => {
		const authoritative = versionConflict?.authoritative;
		if (!authoritative) return;
		const nextRows = editableRowsFromEstimate(authoritative);
		const nextSnapshot = JSON.stringify({
			title: authoritative.estimateTitle,
			rows: nextRows,
		});
		setVersion(authoritative.version);
		setTitle(authoritative.estimateTitle);
		setRegion(authoritative.estimateRegion);
		setAssumptions(authoritative.assumptions);
		setPricing(authoritative.pricing);
		setRows(nextRows);
		setSavedSnapshot(nextSnapshot);
		hasLocalEdits.current = false;
		setVersionConflict(null);
		setSaveMessage("");
		setSaveRetryAttempt(0);
		setSaveErrorRetryable(false);
		setSaveState("saved");
	}, [versionConflict]);

	const rebaseLocalDraft = useCallback(() => {
		const authoritative = versionConflict?.authoritative;
		if (!authoritative) return;
		setVersion(authoritative.version);
		setRegion(authoritative.estimateRegion);
		setAssumptions(authoritative.assumptions);
		setPricing(authoritative.pricing);
		setSavedSnapshot(JSON.stringify(draftSnapshotFromEstimate(authoritative)));
		hasLocalEdits.current = true;
		setVersionConflict(null);
		setSaveMessage("");
		setSaveRetryAttempt(0);
		setSaveErrorRetryable(false);
		setSaveState("idle");
	}, [versionConflict]);

	const applyPricedEstimate = useCallback(
		(next: EstimateWidgetProps, message: string) => {
			const nextRows = next.rows.map(
				({ lineTotal: _lineTotal, ...row }) => row,
			);
			setVersion(next.version);
			setTitle(next.estimateTitle);
			setRegion(next.estimateRegion);
			setAssumptions(next.assumptions);
			setPricing(next.pricing);
			setRows(nextRows);
			setSavedSnapshot(
				JSON.stringify({ title: next.estimateTitle, rows: nextRows }),
			);
			hasLocalEdits.current = false;
			setSaveState("saved");
			setActionMessage(message);
			setOfferRowId(null);
			announceDocumentsChanged();
		},
		[],
	);

	const refreshOfficialPrices = useCallback(async () => {
		if (dirty || priceRefreshState === "checking") return;
		setPriceRefreshState("checking");
		setActionMessage("Проверяю материалы по ФГИС ЦС…");
		try {
			const response = await fetch(
				`/api/v3/projects/${encodeURIComponent(initial.projectId)}/estimate/prices/refresh`,
				{
					method: "POST",
					headers: withCsrfHeader({
						Accept: "application/json",
						"Content-Type": "application/json",
						"Idempotency-Key": `fgis-refresh-${globalThis.crypto.randomUUID()}`,
					}),
					body: JSON.stringify({ version }),
					credentials: "same-origin",
					cache: "no-store",
				},
			);
			if (!response.ok) {
				throw new Error(await readResponseError(response));
			}
			const value: unknown = await response.json();
			const record =
				typeof value === "object" && value !== null
					? (value as Record<string, unknown>)
					: null;
			const parsed =
				kolibriGenerativeUIComponentSchemas.EstimateEditor.safeParse(
					record?.estimate,
				);
			if (!parsed.success) {
				throw new Error("Сервер вернул смету неизвестного формата.");
			}
			applyPricedEstimate(
				parsed.data,
				typeof record?.message === "string"
					? record.message
					: "Проверка цен завершена.",
			);
			setPriceRefreshState("idle");
		} catch (caught) {
			setActionMessage(
				caught instanceof Error ? caught.message : "Не удалось проверить цены.",
			);
			setPriceRefreshState("error");
		}
	}, [
		applyPricedEstimate,
		dirty,
		initial.projectId,
		priceRefreshState,
		version,
	]);

	useEffect(() => {
		if (
			!dirty ||
			!valid ||
			saveState === "saving" ||
			saveState === "conflict" ||
			versionConflict
		) {
			return;
		}
		if (saveState === "error" && !saveErrorRetryable) return;
		const retryDelay =
			saveState === "error"
				? Math.min(1_000 * 2 ** Math.max(0, saveRetryAttempt - 1), 10_000)
				: 700;
		const timeout = window.setTimeout(() => void save(), retryDelay);
		return () => window.clearTimeout(timeout);
	}, [
		dirty,
		save,
		saveErrorRetryable,
		saveRetryAttempt,
		saveState,
		valid,
		versionConflict,
	]);

	return (
		<section
			data-slot="estimate-editor"
			className={
				presentation === "inline"
					? "overflow-visible border-t border-border bg-card min-[960px]:overflow-hidden"
					: "overflow-visible border border-border bg-card min-[960px]:overflow-hidden min-[960px]:rounded-xl"
			}
			aria-label="Редактор сметы"
		>
			<header className="grid items-start gap-3 border-b border-border px-4 py-3 min-[960px]:grid-cols-[minmax(0,1fr)_auto]">
				<div className="min-w-0 flex-1">
					<label
						className="sr-only"
						htmlFor={`estimate-title-${initial.documentId}`}
					>
						Название сметы
					</label>
					<input
						id={`estimate-title-${initial.documentId}`}
						className="min-h-11 w-full rounded-md bg-transparent px-1 py-1 text-base font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring min-[960px]:min-h-0 min-[960px]:py-0.5 min-[960px]:text-sm"
						value={title}
						maxLength={240}
						onChange={(event) => {
							hasLocalEdits.current = true;
							setTitle(event.target.value);
							setSaveState((current) =>
								current === "conflict" ? current : "idle",
							);
						}}
					/>
					<p className="mt-0.5 px-1 text-xs text-muted-foreground">
						Черновик · версия {version}
						{region ? ` · ${region}` : ""}
					</p>
				</div>
				<div className="rounded-2xl bg-muted/40 px-3 py-2 text-left min-[960px]:bg-transparent min-[960px]:p-0 min-[960px]:text-right">
					<p className="text-[11px] text-muted-foreground">Итого</p>
					<p className="text-lg font-semibold tabular-nums">
						{formatMoney(total)}
					</p>
				</div>
			</header>

			{versionConflict ? (
				<section
					data-slot="estimate-version-conflict"
					className="border-b border-amber-300 bg-amber-50 px-4 py-4 text-amber-950 dark:border-amber-900 dark:bg-amber-950/35 dark:text-amber-100"
					role="alert"
					aria-live="assertive"
				>
					<div className="flex items-start gap-3">
						<RefreshCwIcon
							aria-hidden="true"
							className="mt-0.5 size-4 shrink-0"
						/>
						<div className="min-w-0 flex-1">
							<h3 className="text-sm font-semibold">
								Смета изменилась в другом окне
							</h3>
							<p className="mt-1 text-xs leading-5">
								Редактор открыт на версии {versionConflict.expectedVersion},
								сервер уже на версии {versionConflict.currentVersion}. Ваш
								локальный черновик сохранён в редакторе и не был заменён.
							</p>
							{versionConflict.diff ? (
								<div
									data-slot="estimate-conflict-diff"
									className="mt-3 grid gap-3 rounded-xl border border-amber-300/70 bg-background/70 p-3 text-foreground min-[700px]:grid-cols-3 dark:border-amber-800"
								>
									<EstimateConflictItems
										items={versionConflict.diff.localChanges}
										label="В вашем черновике"
									/>
									<EstimateConflictItems
										items={versionConflict.diff.remoteChanges}
										label="На сервере"
									/>
									<EstimateConflictItems
										items={versionConflict.diff.conflicts}
										label="Требуют выбора"
									/>
									{versionConflict.diff.localChanges.length === 0 &&
									versionConflict.diff.remoteChanges.length === 0 ? (
										<p className="text-xs text-muted-foreground">
											Содержимое совпадает; различается только номер версии.
										</p>
									) : null}
								</div>
							) : (
								<p className="mt-2 text-xs">{saveMessage}</p>
							)}
							<div className="mt-3 flex flex-col gap-2 min-[700px]:flex-row min-[700px]:flex-wrap">
								{versionConflict.authoritative ? (
									<>
										<Button
											type="button"
											size="sm"
											variant="outline"
											onClick={useAuthoritativeVersion}
										>
											Загрузить версию {versionConflict.currentVersion}
										</Button>
										<Button type="button" size="sm" onClick={rebaseLocalDraft}>
											Сохранить мой черновик поверх версии{" "}
											{versionConflict.currentVersion}
										</Button>
									</>
								) : (
									<Button
										type="button"
										size="sm"
										variant="outline"
										onClick={() => void refreshVersionConflict()}
									>
										Повторить загрузку сравнения
									</Button>
								)}
							</div>
							{versionConflict.authoritative ? (
								<p className="mt-2 text-[11px] leading-4 text-muted-foreground">
									Загрузка серверной версии заменит поля редактора. Сохранение
									черновика создаст следующую версию после явного выбора.
								</p>
							) : null}
						</div>
					</div>
				</section>
			) : null}

			<div className="flex flex-col items-stretch gap-2 border-b border-border bg-muted/15 px-4 py-3 min-[960px]:flex-row min-[960px]:items-center min-[960px]:justify-between min-[960px]:py-2.5">
				<div className="flex min-w-0 items-center gap-2 text-xs">
					{priceRefreshState === "checking" ? (
						<LoaderCircleIcon
							aria-hidden="true"
							className="size-4 shrink-0 animate-spin text-muted-foreground"
						/>
					) : pricing.status === "sourced" ? (
						<CheckCircle2Icon
							aria-hidden="true"
							className="size-4 shrink-0 text-emerald-600"
						/>
					) : (
						<RefreshCwIcon
							aria-hidden="true"
							className="size-4 shrink-0 text-muted-foreground"
						/>
					)}
					<span className="truncate text-muted-foreground">{pricingLabel}</span>
				</div>
				<Button
					type="button"
					variant="outline"
					size="sm"
					disabled={
						dirty || materialRowCount === 0 || priceRefreshState === "checking"
					}
					onClick={() => void refreshOfficialPrices()}
					className="min-h-11 w-full min-[960px]:min-h-0 min-[960px]:w-auto"
				>
					<RefreshCwIcon
						aria-hidden="true"
						className={`size-4 ${
							priceRefreshState === "checking" ? "animate-spin" : ""
						}`}
					/>
					Проверить цены материалов
				</Button>
			</div>

			{assumptions.length > 0 ? (
				<div className="border-b border-border bg-muted/20 px-4 py-2.5 text-xs">
					<details>
						<summary className="cursor-pointer select-none font-medium text-foreground">
							Предварительный расчёт · допущений: {assumptions.length}
						</summary>
						<ul className="mt-2 space-y-1 pl-4 text-muted-foreground">
							{assumptions.map((assumption) => (
								<li key={assumption} className="list-disc">
									{assumption}
								</li>
							))}
						</ul>
					</details>
				</div>
			) : null}

			<div
				data-slot="estimate-mobile-list"
				className="space-y-3 bg-muted/10 p-3 pb-28 min-[960px]:hidden"
			>
				{rows.length === 0 ? (
					<div className="rounded-3xl border border-dashed border-border bg-background px-5 py-10 text-center text-sm text-muted-foreground">
						Позиций пока нет. Добавьте первую строку — расчёт появится
						автоматически.
					</div>
				) : (
					rows.map((row, index) => (
						<article
							key={row.id}
							className="overflow-hidden rounded-3xl border border-border bg-background p-4 shadow-sm"
							aria-labelledby={`estimate-mobile-row-${row.id}`}
						>
							<div className="flex min-w-0 items-start gap-2">
								<span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-sm font-semibold tabular-nums">
									{index + 1}
								</span>
								<div className="min-w-0 flex-1 pt-0.5">
									<p
										id={`estimate-mobile-row-${row.id}`}
										className="truncate text-xs font-semibold tracking-wide text-muted-foreground uppercase"
									>
										{row.section} · {estimateKindLabel(row.kind)}
									</p>
									<p
										className={cn(
											"mt-1 truncate text-xs",
											row.priceEvidence?.status === "stale" ||
												(!row.priceEvidence &&
													!row.enginePriceProvenance?.verified)
												? "text-amber-700 dark:text-amber-400"
												: "text-emerald-700 dark:text-emerald-400",
										)}
									>
										{row.priceEvidence
											? priceSourceLabel(row.priceEvidence)
											: row.enginePriceProvenance
												? enginePriceSourceLabel(row.enginePriceProvenance)
												: "Источник не указан"}
									</p>
								</div>
								<Button
									type="button"
									variant="ghost"
									size="icon"
									className="size-11 shrink-0 rounded-full"
									aria-label={`Удалить позицию ${index + 1}`}
									onClick={() => {
										hasLocalEdits.current = true;
										setRows((current) =>
											current.filter((item) => item.id !== row.id),
										);
										setSaveState((current) =>
											current === "conflict" ? current : "idle",
										);
									}}
								>
									<Trash2Icon aria-hidden="true" className="size-5" />
								</Button>
							</div>

							<label className="mt-3 block text-xs font-medium text-muted-foreground">
								Работа или материал
								<input
									aria-label={`Наименование позиции ${index + 1}`}
									className="mt-1 min-h-12 w-full rounded-2xl border border-input bg-background px-3 py-2 text-base outline-none focus:ring-2 focus:ring-ring"
									placeholder="Введите наименование"
									value={row.description}
									maxLength={300}
									enterKeyHint="next"
									onChange={(event) =>
										updateRow(row.id, "description", event.target.value)
									}
								/>
							</label>

							<div className="mt-3 grid grid-cols-2 gap-2.5">
								<label className="text-xs font-medium text-muted-foreground">
									Единица
									<input
										aria-label={`Единица позиции ${index + 1}`}
										className="mt-1 min-h-12 w-full rounded-2xl border border-input bg-background px-3 py-2 text-base text-foreground outline-none focus:ring-2 focus:ring-ring"
										value={row.unit}
										maxLength={32}
										enterKeyHint="next"
										onChange={(event) =>
											updateRow(row.id, "unit", event.target.value)
										}
									/>
								</label>
								<label className="text-xs font-medium text-muted-foreground">
									Количество
									<input
										aria-label={`Количество позиции ${index + 1}`}
										inputMode="decimal"
										enterKeyHint="next"
										className="mt-1 min-h-12 w-full rounded-2xl border border-input bg-background px-3 py-2 text-right text-base text-foreground tabular-nums outline-none focus:ring-2 focus:ring-ring"
										value={row.quantity}
										onChange={(event) =>
											updateRow(row.id, "quantity", event.target.value)
										}
									/>
								</label>
								<label className="text-xs font-medium text-muted-foreground">
									Цена
									<input
										aria-label={`Цена позиции ${index + 1}`}
										inputMode="decimal"
										enterKeyHint="done"
										className="mt-1 min-h-12 w-full rounded-2xl border border-input bg-background px-3 py-2 text-right text-base text-foreground tabular-nums outline-none focus:ring-2 focus:ring-ring"
										value={row.unitPrice}
										onChange={(event) =>
											updateRow(row.id, "unitPrice", event.target.value)
										}
									/>
								</label>
								<div className="text-xs font-medium text-muted-foreground">
									Сумма
									<output className="mt-1 flex min-h-12 items-center justify-end rounded-2xl bg-muted px-3 py-2 text-base font-semibold text-foreground tabular-nums">
										{formatMoney(toAmount(row.quantity, row.unitPrice))}
									</output>
								</div>
							</div>

							<EstimateRowEvidence
								row={row}
								className="mt-2 border-t border-border text-xs"
							/>

							<Button
								type="button"
								variant="outline"
								className="min-h-11 w-full rounded-2xl"
								disabled={dirty}
								onClick={() =>
									setOfferRowId((current) =>
										current === row.id ? null : row.id,
									)
								}
							>
								{offerRowId === row.id
									? "Скрыть предложение"
									: "Цена поставщика"}
							</Button>

							{offerRowId === row.id ? (
								<SupplierOfferForm
									projectId={initial.projectId}
									row={row}
									version={version}
									onApplied={applyPricedEstimate}
								/>
							) : null}
						</article>
					))
				)}
			</div>

			<div className="hidden overflow-x-auto min-[960px]:block">
				<table className="w-full min-w-[700px] border-collapse text-sm">
					<caption className="sr-only">Редактируемые позиции сметы</caption>
					<thead>
						<tr className="border-b border-border bg-muted/30 text-left text-[11px] font-medium text-muted-foreground">
							<th className="w-10 px-2 py-2 text-center">№</th>
							<th className="min-w-64 px-2 py-2">Работа или материал</th>
							<th className="w-24 px-2 py-2">Ед.</th>
							<th className="w-28 px-2 py-2 text-right">Кол-во</th>
							<th className="w-36 px-2 py-2 text-right">Цена</th>
							<th className="w-36 px-2 py-2 text-right">Сумма</th>
							<th className="w-10 px-1 py-2">
								<span className="sr-only">Действия</span>
							</th>
						</tr>
					</thead>
					<tbody>
						{rows.length === 0 ? (
							<tr>
								<td
									colSpan={7}
									className="px-4 py-8 text-center text-sm text-muted-foreground"
								>
									Позиций пока нет. Добавьте первую строку — расчёт появится
									автоматически.
								</td>
							</tr>
						) : (
							rows.map((row, index) => (
								<Fragment key={row.id}>
									<tr className="border-b border-border last:border-0">
										<td className="px-2 py-1.5 text-center text-xs text-muted-foreground">
											{index + 1}
										</td>
										<td className="px-2 py-1.5">
											<div className="mb-0.5 flex items-center gap-2 px-2 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
												<span>{row.section}</span>
												<span aria-hidden="true">·</span>
												<span>
													{row.kind === "work"
														? "работа"
														: row.kind === "material"
															? "материал"
															: row.kind === "equipment"
																? "оборудование"
																: "услуга"}
												</span>
												{row.priceEvidence ? (
													<>
														<span aria-hidden="true">·</span>
														<span
															className={
																row.priceEvidence.status === "stale"
																	? "text-amber-700"
																	: "text-emerald-700"
															}
														>
															{priceSourceLabel(row.priceEvidence)}
														</span>
													</>
												) : row.enginePriceProvenance ? (
													<>
														<span aria-hidden="true">·</span>
														<span
															className={
																row.enginePriceProvenance.verified
																	? "text-emerald-700"
																	: "text-amber-700"
															}
														>
															{enginePriceSourceLabel(
																row.enginePriceProvenance,
															)}
														</span>
													</>
												) : (
													<>
														<span aria-hidden="true">·</span>
														<span className="text-amber-700">
															Источник не указан
														</span>
													</>
												)}
											</div>
											<input
												aria-label={`Наименование позиции ${index + 1}`}
												className="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 outline-none hover:border-border focus:border-border focus:ring-2 focus:ring-ring"
												placeholder="Введите наименование"
												value={row.description}
												maxLength={300}
												onChange={(event) =>
													updateRow(row.id, "description", event.target.value)
												}
											/>
											<details className="px-2 pt-0.5 text-[10px] text-muted-foreground">
												<summary className="cursor-pointer select-none">
													Основание количества и цены
												</summary>
												<p className="mt-1">Количество: {row.quantityBasis}</p>
												<p>Цена: {row.priceBasis}</p>
												{row.priceEvidence ? (
													<div className="mt-1 space-y-0.5">
														<p>
															Регион: {row.priceEvidence.region}
															{row.priceEvidence.period
																? ` · ${row.priceEvidence.period}`
																: ""}
														</p>
														<p>
															{row.priceEvidence.freshnessBasis ===
															"supplier_valid_until"
																? "Действует до"
																: "Проверить актуальность после"}{" "}
															{row.priceEvidence.freshUntil} ·{" "}
															{row.priceEvidence.taxStatus === "included"
																? "НДС включён"
																: row.priceEvidence.taxStatus === "excluded"
																	? "без НДС"
																	: "НДС не указан"}
														</p>
														{row.priceEvidence.landedCostStatus ===
														"not_calculated" ? (
															<p>
																Справочная цена · доставка и складирование не
																рассчитаны
															</p>
														) : (
															<p>
																Цена с доставкой:{" "}
																{formatMoney(
																	Number(row.priceEvidence.landedUnitPrice),
																)}
															</p>
														)}
														<a
															className="inline-flex text-foreground underline underline-offset-2"
															href={row.priceEvidence.sourceUrl}
															target="_blank"
															rel="noreferrer"
														>
															Источник · {row.priceEvidence.sourceReference}
														</a>
														<p title={row.priceEvidence.snapshotHash}>
															Снимок:{" "}
															{row.priceEvidence.snapshotHash.slice(0, 18)}…
														</p>
													</div>
												) : row.enginePriceProvenance ? (
													<div className="mt-1 space-y-0.5">
														<p
															className={
																row.enginePriceProvenance.verified
																	? "text-emerald-700"
																	: "text-amber-700"
															}
														>
															{enginePriceSourceLabel(
																row.enginePriceProvenance,
															)}
														</p>
														<p>
															{row.enginePriceProvenance.label} ·{" "}
															{row.enginePriceProvenance.reference}
														</p>
														<p>
															Регион: {row.enginePriceProvenance.region} · на{" "}
															{row.enginePriceProvenance.observedAt.slice(
																0,
																10,
															)}
														</p>
														<p>
															{engineVatLabel(
																row.enginePriceProvenance.vatMode,
															)}{" "}
															· уверенность{" "}
															{Math.round(
																Number(row.enginePriceProvenance.confidence) *
																	100,
															)}
															%
														</p>
														{row.enginePriceProvenance.validUntil ? (
															<p>
																Действует до{" "}
																{row.enginePriceProvenance.validUntil.slice(
																	0,
																	10,
																)}
															</p>
														) : null}
														{row.enginePriceProvenance.sourceUrl.startsWith(
															"https://",
														) ? (
															<a
																className="inline-flex text-foreground underline underline-offset-2"
																href={row.enginePriceProvenance.sourceUrl}
																target="_blank"
																rel="noreferrer"
															>
																Открыть источник
															</a>
														) : (
															<p>Источник сохранён в текущем расчёте</p>
														)}
													</div>
												) : (
													<p className="mt-1 text-amber-700">
														Цена введена без подтверждённого источника.
													</p>
												)}
											</details>
											<div className="px-2 pt-1">
												<Button
													type="button"
													variant="ghost"
													size="xs"
													disabled={dirty}
													onClick={() =>
														setOfferRowId((current) =>
															current === row.id ? null : row.id,
														)
													}
												>
													{offerRowId === row.id
														? "Скрыть предложение"
														: "Цена поставщика"}
												</Button>
											</div>
										</td>
										<td className="px-2 py-1.5">
											<input
												aria-label={`Единица позиции ${index + 1}`}
												className="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 outline-none hover:border-border focus:border-border focus:ring-2 focus:ring-ring"
												value={row.unit}
												maxLength={32}
												onChange={(event) =>
													updateRow(row.id, "unit", event.target.value)
												}
											/>
										</td>
										<td className="px-2 py-1.5">
											<input
												aria-label={`Количество позиции ${index + 1}`}
												inputMode="decimal"
												className="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-right tabular-nums outline-none hover:border-border focus:border-border focus:ring-2 focus:ring-ring"
												value={row.quantity}
												onChange={(event) =>
													updateRow(row.id, "quantity", event.target.value)
												}
											/>
										</td>
										<td className="px-2 py-1.5">
											<input
												aria-label={`Цена позиции ${index + 1}`}
												inputMode="decimal"
												className="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-right tabular-nums outline-none hover:border-border focus:border-border focus:ring-2 focus:ring-ring"
												value={row.unitPrice}
												onChange={(event) =>
													updateRow(row.id, "unitPrice", event.target.value)
												}
											/>
										</td>
										<td className="px-2 py-1.5 text-right font-medium tabular-nums">
											{formatMoney(toAmount(row.quantity, row.unitPrice))}
										</td>
										<td className="px-1 py-1.5">
											<Button
												type="button"
												variant="ghost"
												size="icon-sm"
												aria-label={`Удалить позицию ${index + 1}`}
												onClick={() => {
													hasLocalEdits.current = true;
													setRows((current) =>
														current.filter((item) => item.id !== row.id),
													);
													setSaveState((current) =>
														current === "conflict" ? current : "idle",
													);
												}}
											>
												<Trash2Icon aria-hidden="true" className="size-4" />
											</Button>
										</td>
									</tr>
									{offerRowId === row.id ? (
										<tr className="border-b border-border bg-muted/10">
											<td colSpan={7} className="px-4 py-3">
												<SupplierOfferForm
													projectId={initial.projectId}
													row={row}
													version={version}
													onApplied={applyPricedEstimate}
												/>
											</td>
										</tr>
									) : null}
								</Fragment>
							))
						)}
					</tbody>
				</table>
			</div>

			<footer
				data-slot="estimate-editor-footer"
				className="sticky bottom-0 z-20 flex flex-wrap items-center justify-between gap-3 border-t border-border bg-card px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] min-[960px]:static min-[960px]:pb-3"
			>
				<div
					data-slot="estimate-editor-footer-actions"
					className="flex min-w-0 flex-wrap items-center gap-2"
				>
					<Button
						data-slot="estimate-add-row-action"
						type="button"
						variant="outline"
						size="sm"
						className="min-h-11 flex-1 rounded-2xl min-[960px]:min-h-0 min-[960px]:flex-none min-[960px]:rounded-md"
						onClick={() => {
							hasLocalEdits.current = true;
							setRows((current) => [...current, emptyRow()]);
							setSaveState((current) =>
								current === "conflict" ? current : "idle",
							);
						}}
					>
						<PlusIcon aria-hidden="true" className="size-4" />
						Позиция
					</Button>
					<span
						className={`min-w-0 flex-1 text-xs ${
							saveState === "error"
								? "text-destructive"
								: versionConflict
									? "text-amber-700 dark:text-amber-300"
									: "text-muted-foreground"
						}`}
						role={saveState === "error" || versionConflict ? "alert" : "status"}
					>
						{saveState === "saving" ? (
							<LoaderCircleIcon
								aria-hidden="true"
								className="size-3.5 shrink-0 animate-spin"
							/>
						) : null}
						{versionConflict
							? `Нужно выбрать версию · локальный черновик сохранён`
							: saveState === "error"
								? saveMessage
								: saveState === "saving"
									? "Сохраняю изменения…"
									: saveState === "saved"
										? `Автосохранено · версия ${version}`
										: dirty
											? valid
												? "Сохранится автоматически"
												: "Заполните наименование и числовые поля"
											: `Автосохранение включено · версия ${version}`}
					</span>
					{saveState === "error" ? (
						<Button
							type="button"
							variant="ghost"
							size="xs"
							onClick={() => void save()}
						>
							Повторить сохранение
						</Button>
					) : null}
				</div>
			</footer>
			{rows.length > 0 && !dirty ? (
				<div className="flex flex-col items-stretch gap-2 border-t border-border bg-muted/15 px-4 py-3 min-[960px]:flex-row min-[960px]:items-center min-[960px]:justify-between min-[960px]:py-2.5">
					<div className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
						<CheckCircle2Icon
							aria-hidden="true"
							className="size-4 shrink-0 text-emerald-600"
						/>
						<span className="truncate">
							{actionMessage || `Сохранено в проекте · версия ${version}`}
						</span>
					</div>
					<div className="flex flex-wrap items-center gap-2 [&>button]:w-full min-[960px]:[&>button]:w-auto">
						<DropdownMenu>
							<DropdownMenuTrigger asChild>
								<Button type="button" variant="outline" size="sm">
									<DownloadIcon aria-hidden="true" className="size-4" />
									Скачать
									<ChevronDownIcon aria-hidden="true" className="size-3.5" />
								</Button>
							</DropdownMenuTrigger>
							<DropdownMenuContent align="end">
								<DropdownMenuLabel className="text-xs">
									Формат файла
								</DropdownMenuLabel>
								<DropdownMenuSeparator />
								<DropdownMenuItem onSelect={() => downloadEstimate("pdf")}>
									PDF
								</DropdownMenuItem>
								<DropdownMenuItem onSelect={() => downloadEstimate("xlsx")}>
									Excel
								</DropdownMenuItem>
								<DropdownMenuItem onSelect={() => downloadEstimate("docx")}>
									Word
								</DropdownMenuItem>
								<DropdownMenuItem onSelect={() => downloadEstimate("csv")}>
									CSV
								</DropdownMenuItem>
							</DropdownMenuContent>
						</DropdownMenu>
					</div>
				</div>
			) : null}
		</section>
	);
}

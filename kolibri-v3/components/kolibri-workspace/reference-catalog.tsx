"use client";

import { useAssistantContext } from "@assistant-ui/react";
import {
	ArrowLeft,
	Building2,
	Database,
	Hammer,
	LayoutTemplate,
	LoaderCircle,
	type LucideIcon,
	Package,
	Percent,
	RefreshCw,
	Ruler,
	Search,
	TriangleAlert,
} from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { KOLIBRI_DOCUMENTS_CHANGED_EVENT } from "@/lib/workspace-events";

const REFERENCE_CATEGORIES = [
	{ id: "works", label: "Работы", icon: Hammer },
	{ id: "materials", label: "Материалы", icon: Package },
	{ id: "units", label: "Единицы", icon: Ruler },
	{
		id: "indices",
		label: "Индексы и коэффициенты",
		icon: Percent,
	},
	{ id: "counterparties", label: "Контрагенты", icon: Building2 },
	{ id: "templates", label: "Шаблоны", icon: LayoutTemplate },
] as const satisfies ReadonlyArray<{
	id: string;
	label: string;
	icon: LucideIcon;
}>;

type ReferenceCategoryId = (typeof REFERENCE_CATEGORIES)[number]["id"];
type CatalogState = "loading" | "ready" | "error";
type PriceEntryKind = "work" | "material" | "equipment" | "service";

type PersonalPriceEntry = {
	itemKey: string;
	kind: PriceEntryKind;
	description: string;
	region: string;
	unit: string;
	latestPrice: string;
	medianPrice: string;
	lowerQuartile: string;
	upperQuartile: string;
	sampleSize: number;
	latestSource: string;
	latestLifecycle: string;
	latestObservedAt: string;
};

type PersonalPriceCatalog = {
	scope: "personal";
	aggregation: {
		method: "median_iqr";
		crossTenantEnabled: false;
	};
	entries: PersonalPriceEntry[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null;
}

function parsePersonalPriceCatalog(value: unknown): PersonalPriceCatalog {
	if (!isRecord(value) || value.scope !== "personal") {
		throw new Error("Price catalog has an incompatible shape.");
	}
	const aggregation = value.aggregation;
	if (
		!isRecord(aggregation) ||
		aggregation.method !== "median_iqr" ||
		aggregation.crossTenantEnabled !== false ||
		!Array.isArray(value.entries)
	) {
		throw new Error("Price catalog aggregation has an incompatible shape.");
	}
	const entries = value.entries.map((raw): PersonalPriceEntry => {
		if (!isRecord(raw)) {
			throw new Error("Price catalog entry has an incompatible shape.");
		}
		const kind = raw.kind;
		if (
			kind !== "work" &&
			kind !== "material" &&
			kind !== "equipment" &&
			kind !== "service"
		) {
			throw new Error("Price catalog entry kind is invalid.");
		}
		const stringFields = [
			"itemKey",
			"description",
			"region",
			"unit",
			"latestPrice",
			"medianPrice",
			"lowerQuartile",
			"upperQuartile",
			"latestSource",
			"latestLifecycle",
			"latestObservedAt",
		] as const;
		for (const field of stringFields) {
			if (typeof raw[field] !== "string") {
				throw new Error(`Price catalog entry ${field} is invalid.`);
			}
		}
		if (
			typeof raw.sampleSize !== "number" ||
			!Number.isInteger(raw.sampleSize) ||
			raw.sampleSize < 1
		) {
			throw new Error("Price catalog sample size is invalid.");
		}
		return {
			itemKey: raw.itemKey as string,
			kind,
			description: raw.description as string,
			region: raw.region as string,
			unit: raw.unit as string,
			latestPrice: raw.latestPrice as string,
			medianPrice: raw.medianPrice as string,
			lowerQuartile: raw.lowerQuartile as string,
			upperQuartile: raw.upperQuartile as string,
			sampleSize: raw.sampleSize,
			latestSource: raw.latestSource as string,
			latestLifecycle: raw.latestLifecycle as string,
			latestObservedAt: raw.latestObservedAt as string,
		};
	});
	return {
		scope: "personal",
		aggregation: {
			method: "median_iqr",
			crossTenantEnabled: false,
		},
		entries,
	};
}

function formatMoney(value: string) {
	const amount = Number(value);
	if (!Number.isFinite(amount)) return value;
	return new Intl.NumberFormat("ru-RU", {
		style: "currency",
		currency: "RUB",
		maximumFractionDigits: 2,
	}).format(amount);
}

function sourceLabel(source: string) {
	if (source === "contract_price") return "Договор";
	if (source === "customer_approved") return "Принято клиентом";
	if (source === "supplier_offer") return "Предложение";
	if (source === "official_reference") return "Официальный ориентир";
	if (source === "user_edit") return "Личная цена";
	if (source === "ai_preliminary") return "Предварительно AI";
	return source;
}

function categoryEntries(
	entries: readonly PersonalPriceEntry[],
	category: ReferenceCategoryId,
) {
	if (category === "materials") {
		return entries.filter((entry) => entry.kind === "material");
	}
	if (category === "works") {
		return entries.filter((entry) => entry.kind !== "material");
	}
	return [];
}

export function ReferenceCatalog({ onBack }: { onBack?: () => void }) {
	const titleId = useId();
	const [activeCategory, setActiveCategory] =
		useState<ReferenceCategoryId>("works");
	const [catalog, setCatalog] = useState<PersonalPriceCatalog | null>(null);
	const [catalogState, setCatalogState] = useState<CatalogState>("loading");
	const [query, setQuery] = useState("");

	const activeCategoryDefinition =
		REFERENCE_CATEGORIES.find(({ id }) => id === activeCategory) ??
		REFERENCE_CATEGORIES[0];

	const loadCatalog = useCallback(async () => {
		setCatalogState("loading");
		try {
			const response = await fetch("/api/v3/pricing/catalog?limit=100", {
				method: "GET",
				headers: { Accept: "application/json" },
				credentials: "same-origin",
				cache: "no-store",
			});
			if (!response.ok) {
				throw new Error(`Price catalog returned HTTP ${response.status}.`);
			}
			setCatalog(parsePersonalPriceCatalog(await response.json()));
			setCatalogState("ready");
		} catch {
			setCatalogState("error");
		}
	}, []);

	useEffect(() => {
		void loadCatalog();
		const refresh = () => void loadCatalog();
		window.addEventListener(KOLIBRI_DOCUMENTS_CHANGED_EVENT, refresh);
		return () =>
			window.removeEventListener(KOLIBRI_DOCUMENTS_CHANGED_EVENT, refresh);
	}, [loadCatalog]);

	const selectedEntries = useMemo(() => {
		const entries = categoryEntries(catalog?.entries ?? [], activeCategory);
		const normalizedQuery = query.trim().toLocaleLowerCase("ru-RU");
		if (!normalizedQuery) return entries;
		return entries.filter((entry) =>
			[entry.description, entry.region, entry.unit]
				.join(" ")
				.toLocaleLowerCase("ru-RU")
				.includes(normalizedQuery),
		);
	}, [activeCategory, catalog?.entries, query]);

	const units = useMemo(() => {
		const counts = new Map<string, number>();
		for (const entry of catalog?.entries ?? []) {
			counts.set(entry.unit, (counts.get(entry.unit) ?? 0) + 1);
		}
		return [...counts.entries()].sort(([left], [right]) =>
			left.localeCompare(right, "ru"),
		);
	}, [catalog?.entries]);

	useAssistantContext({
		getContext: () =>
			[
				"Контекст личного справочника цен Kolibri. Данные принадлежат текущему tenant и пользователю. Это личная история наблюдений, а не общий рыночный индекс. Межтенантное агрегирование выключено. Официальный ориентир, AI-оценка, личная правка, предложение, принятая клиентом цена и договор имеют разную доказательную силу. Этот контекст read-only и не даёт полномочий изменять цены.",
				JSON.stringify({
					surface: "reference_catalog",
					access: "read_only",
					data_status: catalogState,
					scope: "tenant_user_private",
					cross_tenant_aggregation: false,
					category: {
						id: activeCategoryDefinition.id,
						label: activeCategoryDefinition.label,
					},
					visible_entries: selectedEntries.slice(0, 25),
				}),
			].join("\n"),
	});

	const hasPriceData =
		activeCategory === "works" || activeCategory === "materials";
	const filteredUnits = useMemo(() => {
		if (activeCategory !== "units") return units;
		const normalizedQuery = query.trim().toLocaleLowerCase("ru-RU");
		if (!normalizedQuery) return units;
		return units.filter(([unit]) =>
			unit.toLocaleLowerCase("ru-RU").includes(normalizedQuery),
		);
	}, [query, activeCategory, units]);

	return (
		<section
			className="bg-background flex min-h-0 flex-1 flex-col overflow-hidden"
			aria-labelledby={titleId}
		>
			<header className="border-border/80 flex min-h-14 shrink-0 items-center gap-2 border-b px-2.5 py-2">
				{onBack ? (
					<Button
						type="button"
						variant="ghost"
						size="icon-sm"
						className="size-10 rounded-lg"
						onClick={onBack}
						aria-label="Вернуться к рабочему пространству"
					>
						<ArrowLeft className="size-4" aria-hidden="true" />
					</Button>
				) : null}
				<h2 id={titleId} className="sr-only">
					Справочники
				</h2>
				<Button
					type="button"
					variant="ghost"
					size="icon-sm"
					onClick={() => void loadCatalog()}
					disabled={catalogState === "loading"}
					aria-label="Обновить"
					className="size-10 rounded-lg"
				>
					<RefreshCw
						className={`size-4 ${catalogState === "loading" ? "animate-spin" : ""}`}
						aria-hidden="true"
					/>
				</Button>
			</header>

			<div className="border-border/80 flex shrink-0 flex-col gap-2 border-b px-2.5 py-2.5 @min-[720px]:flex-row @min-[720px]:items-center">
				<label className="min-w-0 @min-[720px]:w-56">
					<span className="sr-only">Раздел справочника</span>
					<select
						value={activeCategory}
						onChange={(event) => {
							setActiveCategory(event.target.value as ReferenceCategoryId);
							setQuery("");
						}}
						className="border-input bg-background text-foreground focus-visible:ring-ring h-9 w-full rounded-lg border px-3 text-xs outline-none focus-visible:ring-2"
					>
						{REFERENCE_CATEGORIES.map(({ id, label }) => (
							<option key={id} value={id}>
								{label}
							</option>
						))}
					</select>
				</label>

				{hasPriceData || activeCategory === "units" ? (
					<label className="relative min-w-0 flex-1">
						<Search
							className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2"
							aria-hidden="true"
						/>
						<span className="sr-only">Поиск по личному справочнику</span>
						<Input
							value={query}
							onChange={(event) => setQuery(event.target.value)}
							placeholder="Поиск по названию, региону или ед."
							className="h-9 pl-9 text-xs"
						/>
					</label>
				) : null}
			</div>

			<div className="min-h-0 flex-1 overflow-auto">
				{catalogState === "loading" && !catalog ? (
					<div className="text-muted-foreground flex min-h-64 flex-1 flex-col items-center justify-center px-5 text-center">
						<LoaderCircle
							className="mb-3 size-5 animate-spin"
							aria-hidden="true"
						/>
						<p className="text-foreground text-xs font-medium">
							Загружаю личный справочник
						</p>
					</div>
				) : catalogState === "error" && !catalog ? (
					<div
						className="text-muted-foreground flex min-h-64 flex-1 flex-col items-center justify-center px-5 text-center"
						role="alert"
					>
						<TriangleAlert className="mb-3 size-5" aria-hidden="true" />
						<p className="text-foreground text-xs font-medium">
							Не удалось загрузить справочник
						</p>
						<p className="mt-1 max-w-sm text-[10px] leading-relaxed">
							Данные не подменены пустым результатом. Проверьте соединение и
							повторите загрузку.
						</p>
						<Button
							type="button"
							size="sm"
							variant="outline"
							className="mt-3"
							onClick={() => void loadCatalog()}
						>
							Повторить
						</Button>
					</div>
				) : activeCategory === "units" ? (
					filteredUnits.length > 0 ? (
						<ul className="divide-border/30 divide-y">
							{filteredUnits.map(([unit, count]) => (
								<li
									key={unit}
									className="px-3 py-2.5 text-xs hover:bg-muted/45"
								>
									<div className="flex items-baseline justify-between gap-3">
										<span className="text-foreground font-medium">{unit}</span>
										<span className="text-muted-foreground tabular-nums">
											{count} {count === 1 ? "позиция" : "позиций"}
										</span>
									</div>
								</li>
							))}
						</ul>
					) : (
						<EmptyCatalogState
							title="Единицы появятся вместе с ценами"
							description="Создайте смету или прикрепите предложение к её строке."
						/>
					)
				) : hasPriceData ? (
					selectedEntries.length > 0 ? (
						<ul className="divide-border/30 divide-y">
							{selectedEntries.map((entry) => (
								<li
									key={`${entry.itemKey}:${entry.region}`}
									className="px-3 py-2.5 text-xs hover:bg-muted/45"
								>
									<div className="flex items-start justify-between gap-2">
										<div className="min-w-0 flex-1">
											<p className="text-foreground truncate font-medium">
												{entry.description}
											</p>
											<p className="text-muted-foreground mt-0.5 text-[10px]">
												Регион: {entry.region} · Ед.: {entry.unit} ·{" "}
												{entry.sampleSize} наблюдений · диапазон{" "}
												{formatMoney(entry.lowerQuartile)}–
												{formatMoney(entry.upperQuartile)}
											</p>
										</div>
										<p className="text-foreground min-w-[8.5rem] text-right tabular-nums">
											<span className="block font-medium">
												{formatMoney(entry.medianPrice)}
											</span>
											<span className="text-muted-foreground mt-0.5 block text-[10px]">
												{sourceLabel(entry.latestSource)}
											</span>
										</p>
									</div>
								</li>
							))}
						</ul>
					) : (
						<EmptyCatalogState
							title={query ? "Ничего не найдено" : "Личных цен пока нет"}
							description={
								query
									? "Измените запрос или выберите другой раздел."
									: "Цены появятся после создания и редактирования сметы или прикрепления источника."
							}
						/>
					)
				) : (
					<EmptyCatalogState
						title="Источник раздела ещё не подключён"
						description={`Раздел «${activeCategoryDefinition.label}» будет подключён отдельным проверяемым источником.`}
					/>
				)}
			</div>
		</section>
	);
}

function EmptyCatalogState({
	title,
	description,
}: {
	title: string;
	description: string;
}) {
	return (
		<div className="text-muted-foreground flex min-h-64 flex-1 flex-col items-center justify-center px-5 text-center">
			<Database className="mb-3 size-5" aria-hidden="true" />
			<p className="text-foreground text-xs font-medium">{title}</p>
			<p className="mt-1 max-w-sm text-[10px] leading-relaxed">{description}</p>
		</div>
	);
}

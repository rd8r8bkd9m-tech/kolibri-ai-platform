"use client";

import { CheckCircle2Icon, LoaderCircleIcon, PlusIcon } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
	createEstimateCatalogCandidate,
	searchEstimateCatalog,
	type CatalogAutocompleteEntry,
} from "@/lib/estimate/catalog";
import { cn } from "@/lib/utils";

type CatalogAutocompleteProps = {
	projectId: string;
	region?: string;
	onSelect: (entry: CatalogAutocompleteEntry) => void;
	onCandidateCreated?: () => void;
};

const kindLabels: Record<CatalogAutocompleteEntry["kind"], string> = {
	work: "работа",
	material: "материал",
	equipment: "оборудование",
	service: "услуга",
	overhead: "накладные расходы",
	tax: "налог",
	contingency: "резерв",
};

export function CatalogAutocomplete({
	projectId,
	region,
	onSelect,
	onCandidateCreated,
}: CatalogAutocompleteProps) {
	const listboxId = useId();
	const requestRef = useRef<AbortController | null>(null);
	const [query, setQuery] = useState("");
	const [entries, setEntries] = useState<CatalogAutocompleteEntry[]>([]);
	const [activeIndex, setActiveIndex] = useState(-1);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState("");
	const [candidateKind, setCandidateKind] = useState<CatalogAutocompleteEntry["kind"]>("service");
	const [candidateUnit, setCandidateUnit] = useState("шт.");
	const [candidateSaving, setCandidateSaving] = useState(false);

	useEffect(() => {
		const normalized = query.trim();
		requestRef.current?.abort();
		if (normalized.length < 2) {
			setEntries([]);
			setActiveIndex(-1);
			setLoading(false);
			setError("");
			return;
		}
		const controller = new AbortController();
		requestRef.current = controller;
		const timeout = window.setTimeout(async () => {
			setLoading(true);
			setError("");
			try {
				setEntries(await searchEstimateCatalog(projectId, normalized, region, controller.signal));
				setActiveIndex(-1);
			} catch (caught) {
				if (caught instanceof DOMException && caught.name === "AbortError") return;
				setEntries([]);
				setError(caught instanceof Error ? caught.message : "Не удалось загрузить справочник.");
			} finally {
				if (!controller.signal.aborted) setLoading(false);
			}
		}, 250);
		return () => window.clearTimeout(timeout);
	}, [projectId, query, region]);

	const selectEntry = (entry: CatalogAutocompleteEntry) => {
		onSelect(entry);
		setQuery("");
		setEntries([]);
		setActiveIndex(-1);
	};

	const createCandidate = async () => {
		const originalText = query.trim();
		if (!originalText || candidateSaving) return;
		setCandidateSaving(true);
		setError("");
		try {
			await createEstimateCatalogCandidate(projectId, {
				originalText,
				kind: candidateKind,
				proposedUnit: candidateUnit,
			});
			setError("");
			onCandidateCreated?.();
			setQuery("");
			setEntries([]);
		} catch (caught) {
			setError(caught instanceof Error ? caught.message : "Не удалось отправить позицию на проверку.");
		} finally {
			setCandidateSaving(false);
		}
	};

	const showPanel = query.trim().length >= 2;

	return (
		<div className="relative min-w-0 flex-1" data-slot="estimate-catalog-autocomplete">
			<label className="sr-only" htmlFor={`${listboxId}-input`}>Добавить позицию из справочника</label>
			<Input
				id={`${listboxId}-input`}
				value={query}
				placeholder="Найти работу или материал…"
				role="combobox"
				aria-autocomplete="list"
				aria-controls={listboxId}
				aria-expanded={showPanel}
				aria-activedescendant={activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined}
				className="min-h-10 min-w-44"
				onChange={(event) => setQuery(event.target.value)}
				onKeyDown={(event) => {
					if (event.key === "ArrowDown") {
						event.preventDefault();
						setActiveIndex((current) => Math.min(current + 1, entries.length - 1));
					} else if (event.key === "ArrowUp") {
						event.preventDefault();
						setActiveIndex((current) => Math.max(current - 1, 0));
					} else if (event.key === "Enter" && activeIndex >= 0 && entries[activeIndex]) {
						event.preventDefault();
						selectEntry(entries[activeIndex]);
					} else if (event.key === "Escape") {
						setQuery("");
						setEntries([]);
						setActiveIndex(-1);
					}
				}}
			/>
			{showPanel ? (
				<div className="absolute inset-x-0 top-full z-30 mt-1 overflow-hidden rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-lg" role="presentation">
					{loading ? <p className="flex items-center gap-2 px-3 py-3 text-xs text-muted-foreground"><LoaderCircleIcon aria-hidden="true" className="size-4 animate-spin" />Ищу в утверждённом справочнике…</p> : null}
					{!loading && entries.length > 0 ? (
						<ul id={listboxId} role="listbox" aria-label="Результаты справочника" className="max-h-64 overflow-y-auto">
							{entries.map((entry, index) => (
								<li key={entry.id} id={`${listboxId}-option-${index}`} role="option" aria-selected={index === activeIndex}>
									<button type="button" className={cn("flex min-h-12 w-full items-start justify-between gap-3 rounded-md px-3 py-2 text-left text-sm hover:bg-accent", index === activeIndex && "bg-accent")} onMouseDown={(event) => event.preventDefault()} onClick={() => selectEntry(entry)}>
										<span className="min-w-0"><span className="block truncate font-medium">{entry.canonicalName}</span><span className="block truncate text-xs text-muted-foreground">{kindLabels[entry.kind]} · {entry.canonicalUnit} · {entry.visibility === "system_curated" ? "системный" : "проектный"}</span></span>
										{entry.priceRange ? <span className="shrink-0 text-right text-xs tabular-nums text-muted-foreground"><span className="block">{entry.priceRange.p25}–{entry.priceRange.p75} ₽</span><span className="block">медиана {entry.priceRange.median}</span></span> : <span className="shrink-0 text-xs text-amber-700">цена уточняется</span>}
									</button>
								</li>
							))}
						</ul>
					) : null}
					{!loading && entries.length === 0 ? <p className="px-3 py-2 text-xs text-muted-foreground">Совпадений нет. Можно сохранить позицию только в этой смете или отправить её на review.</p> : null}
					{!loading ? <div className="border-t border-border p-2"><div className="flex items-center gap-2"><Input aria-label="Единица новой позиции" value={candidateUnit} maxLength={32} className="h-8 min-w-0" onChange={(event) => setCandidateUnit(event.target.value)} /><select aria-label="Тип новой позиции" className="h-8 rounded-md border border-input bg-background px-2 text-xs" value={candidateKind} onChange={(event) => setCandidateKind(event.target.value as CatalogAutocompleteEntry["kind"])}><option value="work">работа</option><option value="material">материал</option><option value="equipment">оборудование</option><option value="service">услуга</option><option value="overhead">накладные расходы</option><option value="tax">налог</option><option value="contingency">резерв</option></select><Button type="button" size="sm" variant="outline" disabled={candidateSaving} onClick={() => void createCandidate()}><PlusIcon aria-hidden="true" className="size-4" />На review</Button></div><p className="mt-1 text-[11px] text-muted-foreground">Новая позиция останется кандидатом и не попадёт в общий справочник без проверки.</p></div> : null}
					{error ? <p className="px-3 py-2 text-xs text-destructive" role="alert">{error}</p> : null}
				</div>
			) : null}
			{!showPanel && query ? <span className="sr-only"><CheckCircle2Icon aria-hidden="true" />Введите минимум два символа</span> : null}
		</div>
	);
}

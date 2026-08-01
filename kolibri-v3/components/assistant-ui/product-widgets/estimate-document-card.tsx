"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuiState } from "@assistant-ui/react";
import {
	ChevronDownIcon,
	CopyIcon,
	FileSpreadsheetIcon,
	MoreHorizontalIcon,
	UsersIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuLabel,
	DropdownMenuSeparator,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
	containsEstimateDocument,
	type EstimateWidgetProps,
	type ProjectContextSummary,
} from "./types";
import {
	downloadSavedEstimate,
	loadEstimateDocument,
	loadProjectContextSummary,
	ProjectPartiesPanel,
	EstimateCopyPanel,
} from "./estimate-document-common";
import { EstimateEditorWidget } from "./estimate-editor";
import { formatMoney } from "./helpers";
import {
	announceDocumentsChanged,
	KOLIBRI_DOCUMENTS_CHANGED_EVENT,
	openEstimateInWorkspace,
} from "@/lib/workspace-events";

export function EstimateDocumentCard(initial: EstimateWidgetProps) {
	const currentCard = useAuiState((state) => {
		const latest = [...state.thread.messages]
			.reverse()
			.find((message) =>
				containsEstimateDocument(message.content, initial.documentId),
			);
		return latest?.id === state.message.id;
	});
	const [expanded, setExpanded] = useState(false);
	const [openedOnce, setOpenedOnce] = useState(false);
	const [activePanel, setActivePanel] = useState<"parties" | "copy" | null>(
		null,
	);
	const [estimate, setEstimate] = useState(initial);
	const [projectContext, setProjectContext] =
		useState<ProjectContextSummary | null>(null);

	const refresh = useCallback(async () => {
		try {
			setEstimate(
				await loadEstimateDocument({
					documentId: initial.documentId,
					minimumVersion: initial.version,
					projectId: initial.projectId,
				}),
			);
		} catch {
			// The immutable tool snapshot remains visible while reconnecting.
		}
	}, [initial.documentId, initial.projectId, initial.version]);

	const refreshContext = useCallback(async () => {
		setProjectContext(await loadProjectContextSummary(initial.projectId));
	}, [initial.projectId]);

	useEffect(() => {
		void refresh();
		void refreshContext().catch(() => undefined);
		const handleChange = () => {
			void refresh();
			void refreshContext().catch(() => undefined);
		};
		window.addEventListener(KOLIBRI_DOCUMENTS_CHANGED_EVENT, handleChange);
		return () =>
			window.removeEventListener(KOLIBRI_DOCUMENTS_CHANGED_EVENT, handleChange);
	}, [refresh, refreshContext]);

	useEffect(() => {
		announceDocumentsChanged();
	}, [initial.documentId, initial.version]);

	const toggleExpanded = () => {
		setExpanded((current) => {
			const next = !current;
			if (next) setOpenedOnce(true);
			return next;
		});
	};

	const openEditor = () => {
		if (window.matchMedia("(max-width: 959px)").matches) {
			openEstimateInWorkspace({
				documentId: estimate.documentId,
				projectId: estimate.projectId,
				projectName: projectContext?.projectName,
				title: estimate.estimateTitle,
				version: estimate.version,
			});
			return;
		}
		toggleExpanded();
	};

	if (!currentCard) return null;

	const cardSummary = (
		<>
			<span className="row-span-2 grid size-10 shrink-0 place-items-center rounded-xl bg-muted text-muted-foreground sm:row-auto">
				<FileSpreadsheetIcon aria-hidden="true" className="size-5" />
			</span>
			<span className="min-w-0 flex-1">
				<span className="block truncate text-sm font-semibold">
					{estimate.estimateTitle}
				</span>
				{projectContext ? (
					<span className="mt-0.5 block truncate text-xs text-muted-foreground">
						{projectContext.projectName}
						{projectContext.objectName ? ` · ${projectContext.objectName}` : ""}
						{projectContext.client
							? ` · клиент: ${projectContext.client.displayName}`
							: ""}
						{projectContext.contractor
							? ` · подрядчик: ${projectContext.contractor.displayName}`
							: ""}
					</span>
				) : null}
				<span className="mt-0.5 block text-xs text-muted-foreground">
					Документы → Сметы · {estimate.rows.length} поз. · версия{" "}
					{estimate.version}
				</span>
			</span>
			<span className="col-start-2 row-start-2 min-w-0 text-left sm:min-w-28 sm:text-right">
				<span className="block text-[11px] text-muted-foreground">Итого</span>
				<span className="block text-base font-semibold tabular-nums">
					{formatMoney(estimate.totals.total)}
				</span>
			</span>
			{!expanded ? (
				<ChevronDownIcon
					aria-hidden="true"
					className="col-start-3 row-span-2 row-start-1 size-4 shrink-0 self-center text-muted-foreground sm:col-auto sm:row-auto"
				/>
			) : null}
		</>
	);

	return (
		<section
			className="overflow-hidden rounded-2xl border border-border bg-card"
			aria-label="Смета проекта"
		>
			<div className="flex min-w-0 items-stretch">
				{expanded ? (
					<div className="grid min-w-0 flex-1 grid-cols-[2.5rem_minmax(0,1fr)_auto] gap-x-3 gap-y-1.5 p-4 text-left sm:flex sm:items-center sm:gap-3">
						{cardSummary}
					</div>
				) : (
					<button
						type="button"
						className="grid min-w-0 flex-1 grid-cols-[2.5rem_minmax(0,1fr)_auto] gap-x-3 gap-y-1.5 p-4 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset sm:flex sm:items-center sm:gap-3"
						aria-expanded="false"
						aria-label={`Открыть смету «${estimate.estimateTitle}» для редактирования`}
						onClick={openEditor}
					>
						{cardSummary}
					</button>
				)}
				<DropdownMenu>
					<DropdownMenuTrigger asChild>
						<Button
							type="button"
							size="icon"
							variant="ghost"
							className="my-auto mr-2 shrink-0"
							aria-label="Ещё действия со сметой"
						>
							<MoreHorizontalIcon aria-hidden="true" className="size-4" />
						</Button>
					</DropdownMenuTrigger>
					<DropdownMenuContent align="end" className="w-52">
						<DropdownMenuItem
							onSelect={() =>
								setActivePanel((current) =>
									current === "parties" ? null : "parties",
								)
							}
						>
							<UsersIcon aria-hidden="true" />
							Участники
						</DropdownMenuItem>
						<DropdownMenuItem
							disabled={!projectContext}
							onSelect={() =>
								setActivePanel((current) =>
									current === "copy" ? null : "copy",
								)
							}
						>
							<CopyIcon aria-hidden="true" />
							Повторить для клиента
						</DropdownMenuItem>
						<DropdownMenuSeparator />
						<DropdownMenuLabel className="text-xs">Скачать</DropdownMenuLabel>
						<DropdownMenuItem
							onSelect={() => downloadSavedEstimate(estimate.projectId, "pdf")}
						>
							PDF
						</DropdownMenuItem>
						<DropdownMenuItem
							onSelect={() => downloadSavedEstimate(estimate.projectId, "xlsx")}
						>
							Excel
						</DropdownMenuItem>
						<DropdownMenuItem
							onSelect={() => downloadSavedEstimate(estimate.projectId, "docx")}
						>
							Word
						</DropdownMenuItem>
						<DropdownMenuItem
							onSelect={() => downloadSavedEstimate(estimate.projectId, "csv")}
						>
							CSV
						</DropdownMenuItem>
					</DropdownMenuContent>
				</DropdownMenu>
			</div>
			{activePanel && projectContext ? (
				<div className="border-t border-border bg-muted/20 p-4">
					{activePanel === "parties" ? (
						<ProjectPartiesPanel
							projectId={estimate.projectId}
							context={projectContext}
							onSaved={refreshContext}
						/>
					) : (
						<EstimateCopyPanel
							key={`${estimate.documentId}:${estimate.version}`}
							estimate={estimate}
							context={projectContext}
						/>
					)}
				</div>
			) : null}

			{openedOnce ? (
				<div hidden={!expanded}>
					<EstimateEditorWidget {...estimate} presentation="inline" />
					<button
						type="button"
						className="text-muted-foreground hover:bg-muted/50 hover:text-foreground focus-visible:ring-ring flex h-10 w-full items-center justify-center border-t border-border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset"
						aria-expanded="true"
						aria-label={`Свернуть смету «${estimate.estimateTitle}»`}
						onClick={toggleExpanded}
					>
						<ChevronDownIcon aria-hidden="true" className="size-4 rotate-180" />
					</button>
				</div>
			) : null}
		</section>
	);
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { LoaderCircleIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { UsersIcon, CopyIcon } from "lucide-react";
import { EstimateEditorWidget } from "./estimate-editor";
import { KOLIBRI_DOCUMENTS_CHANGED_EVENT } from "@/lib/workspace-events";
import {
	loadEstimateDocument,
	loadProjectContextSummary,
	ProjectPartiesPanel,
	EstimateCopyPanel,
} from "./estimate-document-common";
import { type EstimateWidgetProps, type ProjectContextSummary } from "./types";

export function EstimateDocumentSurface({
	expectedDocumentId,
	expectedVersion,
	projectId,
}: {
	expectedDocumentId: string;
	expectedVersion: number;
	projectId: string;
}) {
	const [estimate, setEstimate] = useState<EstimateWidgetProps | null>(null);
	const estimateRef = useRef<EstimateWidgetProps | null>(null);
	const loadSequenceRef = useRef(0);
	const [projectContext, setProjectContext] =
		useState<ProjectContextSummary | null>(null);
	const [activePanel, setActivePanel] = useState<"parties" | "copy" | null>(
		null,
	);
	const [error, setError] = useState("");

	const refreshContext = useCallback(async () => {
		setProjectContext(await loadProjectContextSummary(projectId));
	}, [projectId]);

	useEffect(() => {
		let active = true;
		const refreshEstimate = () => {
			const sequence = ++loadSequenceRef.current;
			void loadEstimateDocument({
				documentId: expectedDocumentId,
				minimumVersion: expectedVersion,
				projectId,
			})
				.then((value) => {
					if (!active || sequence !== loadSequenceRef.current) return;
					estimateRef.current = value;
					setEstimate(value);
					setError("");
				})
				.catch((reason: unknown) => {
					if (
						active &&
						sequence === loadSequenceRef.current &&
						estimateRef.current === null
					) {
						setError(
							reason instanceof Error
								? reason.message
								: "Не удалось открыть смету.",
						);
					}
				});
		};
		setError("");
		refreshEstimate();
		void refreshContext().catch(() => undefined);
		const handleDocumentsChanged = () => {
			refreshEstimate();
			void refreshContext().catch(() => undefined);
		};
		window.addEventListener(
			KOLIBRI_DOCUMENTS_CHANGED_EVENT,
			handleDocumentsChanged,
		);
		return () => {
			active = false;
			window.removeEventListener(
				KOLIBRI_DOCUMENTS_CHANGED_EVENT,
				handleDocumentsChanged,
			);
		};
	}, [expectedDocumentId, expectedVersion, projectId, refreshContext]);

	if (error) {
		return (
			<div className="text-destructive flex min-h-48 items-center justify-center p-6 text-sm">
				{error}
			</div>
		);
	}
	if (!estimate) {
		return (
			<div className="text-muted-foreground flex min-h-48 items-center justify-center gap-2 p-6 text-sm">
				<LoaderCircleIcon aria-hidden="true" className="size-4 animate-spin" />
				Загружаю сохранённую смету…
			</div>
		);
	}
	return (
		<div
			data-slot="estimate-document-surface"
			data-document-id={estimate.documentId}
			data-document-version={estimate.version}
			className="min-w-0 space-y-3"
		>
			{projectContext ? (
				<section
					data-slot="estimate-project-context"
					className="overflow-hidden rounded-xl border border-border bg-card"
				>
					<div
						data-slot="estimate-project-context-toolbar"
						className="flex flex-wrap items-center gap-3 px-4 py-3"
					>
						<div
							data-slot="estimate-project-context-summary"
							className="min-w-0 flex-1"
						>
							<p className="truncate text-sm font-medium">
								{projectContext.projectName}
							</p>
							<p className="mt-0.5 truncate text-xs text-muted-foreground">
								{projectContext.objectName ?? "Объект уточняется"}
								{projectContext.client
									? ` · клиент: ${projectContext.client.displayName}`
									: " · клиент не назначен"}
								{projectContext.contractor
									? ` · подрядчик: ${projectContext.contractor.displayName}`
									: ""}
							</p>
						</div>
						<Button
							data-slot="estimate-project-context-action"
							type="button"
							size="sm"
							variant={activePanel === "parties" ? "secondary" : "outline"}
							aria-expanded={activePanel === "parties"}
							onClick={() =>
								setActivePanel((current) =>
									current === "parties" ? null : "parties",
								)
							}
						>
							<UsersIcon aria-hidden="true" className="size-4" />
							Участники
						</Button>
						<Button
							data-slot="estimate-project-context-action"
							type="button"
							size="sm"
							variant={activePanel === "copy" ? "secondary" : "outline"}
							aria-expanded={activePanel === "copy"}
							onClick={() =>
								setActivePanel((current) =>
									current === "copy" ? null : "copy",
								)
							}
						>
							<CopyIcon aria-hidden="true" className="size-4" />
							Повторить
						</Button>
					</div>
					{activePanel ? (
						<div className="border-t border-border bg-muted/20 p-4">
							{activePanel === "parties" ? (
								<ProjectPartiesPanel
									projectId={estimate.projectId}
									context={projectContext}
									onSaved={refreshContext}
								/>
							) : (
								<EstimateCopyPanel
									key={`${estimate.documentId}:${estimate.version}:canvas`}
									estimate={estimate}
									context={projectContext}
								/>
							)}
						</div>
					) : null}
				</section>
			) : null}
			<EstimateEditorWidget {...estimate} presentation="canvas" />
		</div>
	);
}

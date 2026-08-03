"use client";

import { useAuiState } from "@assistant-ui/react";
import {
	AlertCircleIcon,
	CheckCircle2Icon,
	LoaderCircleIcon,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
	ESTIMATE_GENERATION_POLLING_STATUSES,
	estimateGenerationActivityActor,
	estimateGenerationProgressLabel,
	estimateGenerationStatusLabel,
	loadLatestEstimateGeneration,
	selectEstimateGenerationRun,
	type EstimateGenerationActivity,
	type EstimateGenerationRun,
} from "@/lib/estimate/generation";
import { useAcceptedProductChatRun } from "@/lib/product-chat/accepted-run";
import {
	announceDocumentsChanged,
	openEstimateInWorkspace,
} from "@/lib/workspace-events";
import { cn } from "@/lib/utils";

const POLL_INTERVAL_MS = 1_500;
const DISCOVERY_WINDOW_MS = 20_000;
const RETRY_INTERVAL_MS = 3_000;
const autoOpenedRunIds = new Set<string>();
const activityTimeFormatter = new Intl.DateTimeFormat("ru-RU", {
	hour: "2-digit",
	minute: "2-digit",
});

const isActiveProjectId = (value: unknown): value is string =>
	typeof value === "string" &&
	/^project_[A-Za-z0-9._~-]{8,96}$/.test(value);

const ACTIVITY_STATUS_STYLES: Readonly<
	Record<EstimateGenerationActivity["status"], string>
> = {
	queued: "bg-muted-foreground/50",
	working: "animate-pulse bg-sky-500",
	completed: "bg-emerald-500",
	failed: "bg-destructive",
	revision_required: "bg-amber-500",
};

const ACTIVITY_STATUS_LABELS: Readonly<
	Record<EstimateGenerationActivity["status"], string>
> = {
	queued: "в очереди",
	working: "в работе",
	completed: "завершено",
	failed: "ошибка",
	revision_required: "нужна доработка",
};

function EstimateGenerationActivityFeed({
	activity,
}: {
	readonly activity: readonly EstimateGenerationActivity[];
}) {
	if (activity.length === 0) return null;

	return (
		<div
			data-slot="estimate-generation-activity"
			className="mt-2 border-t border-border/70 pt-2"
		>
			<p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
				Ход работы агентов
			</p>
			<ol
				aria-label="Ход работы агентов над сметой"
				className="max-h-44 space-y-1.5 overflow-y-auto pr-1"
			>
				{activity.map((item) => (
					<li
						key={item.id}
						data-activity-role={item.role}
						data-activity-status={item.status}
						className="flex items-start gap-2"
					>
						<span
							aria-hidden="true"
							className="mt-2 flex size-2 shrink-0 items-center justify-center"
						>
							<span
								className={cn(
									"size-1.5 rounded-full",
									ACTIVITY_STATUS_STYLES[item.status],
								)}
							/>
						</span>
						<div className="min-w-0 flex-1 rounded-lg bg-muted/55 px-2.5 py-1.5">
							<div className="flex min-w-0 items-baseline gap-1.5 text-[11px]">
								<span className="shrink-0 font-semibold text-foreground">
									{item.actor}
								</span>
								{item.section ? (
									<span className="min-w-0 truncate text-muted-foreground">
										Раздел: {item.section}
									</span>
								) : null}
								<time
									dateTime={item.createdAt}
									className="ml-auto shrink-0 text-muted-foreground"
								>
									{activityTimeFormatter.format(new Date(item.createdAt))}
								</time>
							</div>
							<p className="mt-0.5 text-xs leading-snug text-foreground/85">
								{item.message}
							</p>
							<span className="sr-only">
								Роль: {estimateGenerationActivityActor(item.role)}. Статус:{" "}
								{ACTIVITY_STATUS_LABELS[item.status]}.
							</span>
						</div>
					</li>
				))}
			</ol>
		</div>
	);
}

export function EstimateGenerationStatus() {
	const activeThreadId = useAuiState((state) => state.threads.mainThreadId);
	const projectId = useAuiState((state) => {
		const thread = state.threads.threadItems.find(
			(candidate) => candidate.id === state.threads.mainThreadId,
		);
		return isActiveProjectId(thread?.custom?.projectId)
			? thread.custom.projectId
			: null;
	});
	const projectName = useAuiState((state) => {
		const thread = state.threads.threadItems.find(
			(candidate) => candidate.id === state.threads.mainThreadId,
		);
		return thread?.title?.trim() || "Проект";
	});
	const chatRunIsActive = useAuiState((state) => state.thread.isRunning);
	const acceptedChatRun = useAcceptedProductChatRun();
	const expectedSourceRunId =
		acceptedChatRun?.threadId === activeThreadId
			? acceptedChatRun.runId
			: null;
	const acceptedAt =
		acceptedChatRun?.threadId === activeThreadId
			? acceptedChatRun.acceptedAt
			: 0;

	const [run, setRun] = useState<EstimateGenerationRun | null>(null);
	const trackedRunIdRef = useRef<string | null>(null);
	const trackedStatusRef = useRef<EstimateGenerationRun["status"] | null>(null);

	useEffect(() => {
		trackedRunIdRef.current = null;
		trackedStatusRef.current = null;
		setRun(null);
	}, [projectId]);

	useEffect(() => {
		if (projectId === null) return;

		let disposed = false;
		let timer: ReturnType<typeof setTimeout> | undefined;
		let request: AbortController | null = null;

		const schedule = (delay: number) => {
			if (disposed) return;
			timer = setTimeout(() => void poll(), delay);
		};

		const shouldKeepDiscovering = () =>
			expectedSourceRunId !== null &&
			Date.now() - acceptedAt < DISCOVERY_WINDOW_MS;

		const poll = async () => {
			request = new AbortController();
			try {
				const summary = await loadLatestEstimateGeneration(
					projectId,
					request.signal,
				);
				if (disposed) return;
				const selected = selectEstimateGenerationRun({
					candidate: summary.generationRun,
					expectedSourceRunId,
					trackedRunId: trackedRunIdRef.current,
				});
				if (selected !== null) {
					trackedRunIdRef.current = selected.id;
					trackedStatusRef.current = selected.status;
					setRun(selected);
				} else if (trackedRunIdRef.current === null) {
					setRun(null);
				}

				const status = selected?.status ?? trackedStatusRef.current;
				const isTerminalStatus =
					status === "failed" || status === "ready" || status === "cancelled";
				if (
					!isTerminalStatus &&
					((status !== null &&
						ESTIMATE_GENERATION_POLLING_STATUSES.has(status)) ||
					chatRunIsActive ||
					shouldKeepDiscovering())
				) {
					schedule(document.hidden ? RETRY_INTERVAL_MS : POLL_INTERVAL_MS);
				}
			} catch (error) {
				if (disposed || (error instanceof DOMException && error.name === "AbortError")) {
					return;
				}
				if (
					chatRunIsActive ||
					shouldKeepDiscovering() ||
					(trackedStatusRef.current !== null &&
						ESTIMATE_GENERATION_POLLING_STATUSES.has(
							trackedStatusRef.current,
						))
				) {
					schedule(RETRY_INTERVAL_MS);
				}
			}
		};

		void poll();
		return () => {
			disposed = true;
			if (timer !== undefined) clearTimeout(timer);
			request?.abort();
		};
	}, [
		acceptedAt,
		chatRunIsActive,
		expectedSourceRunId,
		projectId,
	]);

	// Estimate generation has its own durable AG-UI stream. It is intentionally
	// independent from the chat run: reconnecting EventSource sends the last
	// received event id and the server replays only persisted A2A checkpoints.
	useEffect(() => {
		if (projectId === null || run?.id === undefined) return;
		const cursorKey = `kolibri:estimate-events:${run.id}`;
		const cursor = window.localStorage.getItem(cursorKey);
		const replay = cursor ? `?after=${encodeURIComponent(cursor)}` : "";
		const source = new EventSource(
			`/api/v3/projects/${encodeURIComponent(projectId)}/estimate/generation/${encodeURIComponent(run.id)}/events${replay}`,
		);
		const refreshFromJournal = (event: MessageEvent<string>) => {
			try {
				const payload = JSON.parse(event.data) as { sequence?: number };
				if (typeof payload.sequence === "number") {
					window.localStorage.setItem(cursorKey, String(payload.sequence));
				}
			} catch {
				// The server owns the event schema; malformed data is ignored.
			}
			void loadLatestEstimateGeneration(projectId).then((summary) => {
				setRun((current) =>
					summary.generationRun?.id === current?.id
						? summary.generationRun
						: current,
				);
			});
		};
		source.onmessage = refreshFromJournal;
		return () => source.close();
	}, [projectId, run?.id]);

	const openSavedEstimate = useCallback(() => {
		if (projectId === null || run === null || run.result === null) return;
		announceDocumentsChanged();
		openEstimateInWorkspace({
			documentId: run.result.documentId,
			projectId,
			projectName,
			title: `${projectName} — смета`,
			version: run.result.estimateVersion,
		});
	}, [projectId, projectName, run]);

	useEffect(() => {
		if (run?.status !== "ready" || run.result === null) return;
		if (autoOpenedRunIds.has(run.id)) return;
		autoOpenedRunIds.add(run.id);
		openSavedEstimate();
	}, [openSavedEstimate, run]);

	if (run === null) return null;

	const active = ESTIMATE_GENERATION_POLLING_STATUSES.has(run.status);
	const ready = run.status === "ready" && run.result !== null;
	const attention = run.status === "needs_input" || run.status === "failed";
	const progressLabel = estimateGenerationProgressLabel(run);
	const progressValue =
		run.progress.total > 0
			? Math.min(100, (run.progress.completed / run.progress.total) * 100)
			: undefined;
	const statusLabel = estimateGenerationStatusLabel(run);
	const supportingText =
		run.status === "needs_input"
			? "Ответьте в чате — расчёт продолжится с сохранённого этапа."
			: run.status === "failed"
				? "Исходные данные сохранены. Уточните задачу или повторите запуск в чате."
				: progressLabel;

	return (
		<section
			data-slot="estimate-generation-status"
			data-generation-run-id={run.id}
			data-generation-stage={run.stage}
			data-generation-status={run.status}
			role="status"
			aria-live="polite"
			className={cn(
				"border-border bg-card mx-auto w-full max-w-3xl rounded-xl border px-3 py-2 shadow-sm",
				attention && "border-amber-500/40 bg-amber-500/5",
				ready && "border-emerald-500/35 bg-emerald-500/5",
			)}
		>
			<div className="flex min-w-0 items-center gap-2">
				{active ? (
					<LoaderCircleIcon
						aria-hidden="true"
						className="size-4 shrink-0 animate-spin text-sky-600"
					/>
				) : ready ? (
					<CheckCircle2Icon
						aria-hidden="true"
						className="size-4 shrink-0 text-emerald-600"
					/>
				) : (
					<AlertCircleIcon
						aria-hidden="true"
						className="size-4 shrink-0 text-amber-600"
					/>
				)}
				<div className="min-w-0 flex-1">
					<p className="truncate text-sm font-medium">{statusLabel}</p>
					{supportingText ? (
						<p className="mt-0.5 text-xs text-muted-foreground">
							{supportingText}
						</p>
					) : null}
				</div>
				{ready ? (
					<Button
						type="button"
						size="sm"
						variant="outline"
						className="shrink-0"
						onClick={openSavedEstimate}
					>
						Открыть смету
					</Button>
				) : null}
			</div>
			{active && progressValue !== undefined ? (
				<Progress
					value={progressValue}
					aria-label={progressLabel ?? statusLabel}
					className="mt-2 h-1"
				/>
			) : null}
			<EstimateGenerationActivityFeed activity={run.recentActivity} />
		</section>
	);
}

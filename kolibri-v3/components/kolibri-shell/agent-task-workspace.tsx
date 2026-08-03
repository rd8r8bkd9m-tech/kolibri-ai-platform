"use client";

import {
	Bot,
	CircleStop,
	Clock3,
	MessageSquareText,
	Radio,
	Send,
	TerminalSquare,
	Wrench,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
	AdminDatum,
	AdminEmptyState,
	AdminStatusBadge,
} from "@/components/kolibri-shell/admin/admin-primitives";
import { Button } from "@/components/ui/button";
import {
	applyAgentTaskEvent,
	parseAgentTaskEvent,
	type AgentTaskActivity,
} from "@/lib/platform-admin/agent-task-events";
import {
	agentOperationEventsUrl,
	getAgentOperationDetail,
	type AgentOperation,
	type AgentOperationDetail,
} from "@/lib/platform-admin/agent-operations-client";
import { ProductChatClient } from "@/lib/product-chat/client";
import { cn } from "@/lib/utils";
import { activateAgentTaskInWorkspace } from "@/lib/workspace-events";

type InspectorView = "activity" | "conversation" | "details";

const operationKey = (operation: AgentOperation) =>
	`${operation.task.tenantId}:${operation.task.runId}`;

const statusPresentation = (status: AgentOperation["status"]) =>
	status === "running"
		? { label: "В работе", state: "running" as const }
		: status === "succeeded"
			? { label: "Завершена", state: "ready" as const }
			: { label: "Ошибка", state: "failed" as const };

const formatTime = (value: string) => {
	const date = new Date(value);
	return Number.isNaN(date.getTime())
		? value
		: date.toLocaleString("ru-RU", {
				day: "2-digit",
				month: "2-digit",
				hour: "2-digit",
				minute: "2-digit",
			});
};

export function AgentTaskWorkspace({
	hasMore,
	loadingMore,
	onLoadMore,
	onOperationChanged,
	onSelect,
	operations,
	selectedKey,
}: {
	hasMore: boolean;
	loadingMore: boolean;
	onLoadMore: () => void;
	onOperationChanged: () => void | Promise<void>;
	onSelect: (key: string) => void;
	operations: readonly AgentOperation[];
	selectedKey: string | null;
}) {
	const selected =
		operations.find((operation) => operationKey(operation) === selectedKey) ??
		operations[0] ??
		null;

	if (!operations.length) {
		return (
			<AdminEmptyState text="Агентные задачи по этому запросу не найдены." />
		);
	}

	return (
		<div
			data-slot="agent-task-workspace"
			className="grid min-h-[620px] overflow-hidden rounded-2xl border bg-card lg:grid-cols-[minmax(270px,340px)_minmax(0,1fr)]"
		>
			<aside className="flex min-h-0 flex-col border-b lg:border-r lg:border-b-0">
				<div className="flex h-11 shrink-0 items-center justify-between border-b px-3 text-[11px]">
					<span className="font-medium">Задачи</span>
					<span className="text-muted-foreground">{operations.length}</span>
				</div>
				<div className="max-h-[280px] min-h-0 flex-1 overflow-y-auto overscroll-contain p-2 lg:max-h-[680px]">
					{operations.map((operation) => {
						const key = operationKey(operation);
						const status = statusPresentation(operation.status);
						return (
							<button
								type="button"
								key={key}
								aria-current={key === selectedKey ? "true" : undefined}
								onClick={() => onSelect(key)}
								className={cn(
									"mb-1 w-full rounded-xl px-3 py-3 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-blue-500/40",
									key === selectedKey ? "bg-blue-500/10" : "hover:bg-muted/70",
								)}
							>
								<span className="flex items-start justify-between gap-2">
									<span className="min-w-0">
										<span className="block truncate font-mono text-[11px] font-semibold">
											{operation.task.runId}
										</span>
										<span className="text-muted-foreground mt-1 block truncate text-[10px]">
											{operation.agent.selectedProfile} ·{" "}
											{operation.task.projectId}
										</span>
									</span>
									<AdminStatusBadge label={status.label} state={status.state} />
								</span>
								<span className="text-muted-foreground mt-2 flex items-center justify-between gap-2 text-[10px]">
									<span>{formatTime(operation.timestamps.updatedAt)}</span>
									<span>{operation.lastEventSequence} событий</span>
								</span>
							</button>
						);
					})}
				</div>
				{hasMore ? (
					<Button
						type="button"
						variant="ghost"
						size="sm"
						disabled={loadingMore}
						onClick={onLoadMore}
						className="m-2 shrink-0 rounded-lg"
					>
						{loadingMore ? "Загружаем…" : "Загрузить ещё"}
					</Button>
				) : null}
			</aside>

			{selected ? (
				<AgentTaskInspector
					key={operationKey(selected)}
					onOperationChanged={onOperationChanged}
					operation={selected}
				/>
			) : null}
		</div>
	);
}

function AgentTaskInspector({
	onOperationChanged,
	operation,
}: {
	onOperationChanged: () => void | Promise<void>;
	operation: AgentOperation;
}) {
	const [activeView, setActiveView] = useState<InspectorView>("activity");
	const [detail, setDetail] = useState<AgentOperationDetail | null>(null);
	const [detailError, setDetailError] = useState<string | null>(null);
	const [controlMessage, setControlMessage] = useState<string | null>(null);
	const [cancelling, setCancelling] = useState(false);
	const { activities, streamState } = useAgentTaskActivity(operation);
	const status = statusPresentation(operation.status);

	useEffect(() => {
		const controller = new AbortController();
		void getAgentOperationDetail(operation, controller.signal)
			.then((next) => {
				setDetail(next);
				setDetailError(null);
			})
			.catch((error: unknown) => {
				if (error instanceof DOMException && error.name === "AbortError")
					return;
				setDetailError(
					error instanceof Error ? error.message : "Детали задачи недоступны.",
				);
			});
		return () => controller.abort();
	}, [operation]);

	const bindComposer = () => {
		if (!detail?.control.canUseComposer) return;
		activateAgentTaskInWorkspace({
			projectId: detail.task.projectId,
			runId: detail.task.runId,
			threadId: detail.task.publicThreadId,
		});
		setControlMessage(
			"Общий композер привязан к этому диалогу. Новое поручение будет сохранено в том же проекте.",
		);
	};

	const stopAndCorrect = async () => {
		if (!detail?.control.canCancel || cancelling) return;
		setCancelling(true);
		setControlMessage(null);
		try {
			await new ProductChatClient().cancelRun(operation.task.runId);
			bindComposer();
			setControlMessage(
				"Текущий запуск остановлен. Общий композер привязан к его диалогу — введите исправленное поручение.",
			);
			await onOperationChanged();
		} catch (error) {
			setControlMessage(
				error instanceof Error
					? error.message
					: "Задачу не удалось остановить.",
			);
		} finally {
			setCancelling(false);
		}
	};

	return (
		<section
			className="flex min-h-0 min-w-0 flex-col"
			aria-label="Выбранная агентная задача"
		>
			<header className="shrink-0 border-b px-4 py-4">
				<div className="flex flex-wrap items-start justify-between gap-3">
					<div className="min-w-0">
						<div className="flex items-center gap-2">
							<Bot
								className="text-muted-foreground size-4"
								aria-hidden="true"
							/>
							<h3 className="truncate font-mono text-[13px] font-semibold">
								{operation.task.runId}
							</h3>
							<AdminStatusBadge label={status.label} state={status.state} />
						</div>
						<p className="text-muted-foreground mt-1 truncate text-[10px]">
							{operation.task.tenantId} · {operation.task.projectId}
						</p>
					</div>
					<div className="flex flex-wrap gap-2">
						{detail?.control.canUseComposer ? (
							<Button
								type="button"
								variant="outline"
								size="sm"
								onClick={bindComposer}
								className="rounded-lg shadow-none"
							>
								<Send className="size-4" aria-hidden="true" />
								Дополнить
							</Button>
						) : null}
						{detail?.control.canCancel ? (
							<Button
								type="button"
								variant="outline"
								size="sm"
								disabled={cancelling}
								onClick={() => void stopAndCorrect()}
								className="rounded-lg shadow-none"
							>
								<CircleStop className="size-4" aria-hidden="true" />
								{cancelling ? "Останавливаем…" : "Остановить и скорректировать"}
							</Button>
						) : null}
					</div>
				</div>
				{controlMessage ? (
					<p
						className="mt-3 rounded-lg border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-[11px] text-blue-700 dark:text-blue-300"
						role="status"
					>
						{controlMessage}
					</p>
				) : null}
				{detailError ? (
					<p className="text-destructive mt-3 text-[11px]" role="alert">
						{detailError}
					</p>
				) : null}
			</header>

			<nav
				className="flex h-11 shrink-0 items-end gap-1 border-b px-3"
				aria-label="Данные выбранной задачи"
			>
				<InspectorTab
					active={activeView === "activity"}
					icon={Radio}
					label="Ход работы"
					onClick={() => setActiveView("activity")}
				/>
				<InspectorTab
					active={activeView === "conversation"}
					icon={MessageSquareText}
					label="Диалог"
					onClick={() => setActiveView("conversation")}
				/>
				<InspectorTab
					active={activeView === "details"}
					icon={TerminalSquare}
					label="Детали"
					onClick={() => setActiveView("details")}
				/>
				<span className="text-muted-foreground ml-auto pb-3 text-[10px]">
					{streamState === "live"
						? "Live"
						: streamState === "complete"
							? "Сохранено"
							: "Подключение"}
				</span>
			</nav>

			<div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 lg:max-h-[610px]">
				{activeView === "activity" ? (
					<ActivityFeed activities={activities} />
				) : null}
				{activeView === "conversation" ? (
					<ConversationView activities={activities} detail={detail} />
				) : null}
				{activeView === "details" ? (
					<OperationDetails operation={operation} />
				) : null}
			</div>
		</section>
	);
}

function InspectorTab({
	active,
	icon: Icon,
	label,
	onClick,
}: {
	active: boolean;
	icon: typeof Radio;
	label: string;
	onClick: () => void;
}) {
	return (
		<button
			type="button"
			role="tab"
			aria-selected={active}
			onClick={onClick}
			className={cn(
				"relative flex h-10 items-center gap-1.5 px-2 text-[11px] font-medium",
				active
					? "text-foreground after:absolute after:inset-x-1 after:bottom-0 after:h-0.5 after:bg-blue-600"
					: "text-muted-foreground hover:text-foreground",
			)}
		>
			<Icon className="size-3.5" aria-hidden="true" />
			{label}
		</button>
	);
}

function useAgentTaskActivity(operation: AgentOperation) {
	const [activities, setActivities] = useState<AgentTaskActivity[]>([]);
	const [streamState, setStreamState] = useState<
		"connecting" | "live" | "complete"
	>("connecting");
	const frameRef = useRef<number | null>(null);

	useEffect(() => {
		const byId = new Map<string, AgentTaskActivity>();
		const order: string[] = [];
		setActivities([]);
		setStreamState("connecting");
		const source = new EventSource(agentOperationEventsUrl(operation));
		const flush = () => {
			frameRef.current = null;
			setActivities(order.map((id) => ({ ...byId.get(id)! })));
		};
		const scheduleFlush = () => {
			if (frameRef.current === null) {
				frameRef.current = window.requestAnimationFrame(flush);
			}
		};
		source.onopen = () => setStreamState("live");
		source.onmessage = (message) => {
			let raw: unknown;
			try {
				raw = JSON.parse(message.data) as unknown;
			} catch {
				return;
			}
			const event = parseAgentTaskEvent(raw);
			if (!event) return;
			const terminal = applyAgentTaskEvent(byId, order, event);
			scheduleFlush();
			if (terminal) {
				setStreamState("complete");
				source.close();
			}
		};
		source.onerror = () => {
			if (operation.status !== "running") {
				setStreamState("complete");
				source.close();
			}
		};
		return () => {
			source.close();
			if (frameRef.current !== null) {
				window.cancelAnimationFrame(frameRef.current);
				frameRef.current = null;
			}
		};
	}, [operation.task.runId, operation.task.tenantId, operation.status]);

	return { activities, streamState };
}

function ActivityFeed({
	activities,
}: {
	activities: readonly AgentTaskActivity[];
}) {
	if (!activities.length) {
		return (
			<p className="text-muted-foreground text-[12px]">
				Ожидаем сохранённые события задачи.
			</p>
		);
	}
	return (
		<ol className="space-y-2" aria-label="Ход работы агента">
			{activities.map((activity) => (
				<li key={activity.id}>
					<details
						className="group rounded-xl border bg-background px-3 py-2.5"
						open={!activity.complete}
					>
						<summary className="flex cursor-pointer list-none items-center gap-2 text-[11px]">
							{activity.kind === "tool" ? (
								<Wrench className="size-3.5" aria-hidden="true" />
							) : activity.kind === "message" ? (
								<MessageSquareText className="size-3.5" aria-hidden="true" />
							) : (
								<Clock3 className="size-3.5" aria-hidden="true" />
							)}
							<span className="min-w-0 flex-1 truncate font-medium">
								{activity.title}
							</span>
							<AdminStatusBadge
								label={activity.complete ? "Сохранено" : "В работе"}
								state={activity.tone}
							/>
							<span className="text-muted-foreground font-mono text-[9px]">
								#{activity.sequence}
							</span>
						</summary>
						{activity.content ? (
							<p className="mt-3 whitespace-pre-wrap text-[12px] leading-5">
								{activity.content}
							</p>
						) : null}
						{activity.details ? (
							<ActivityCode label="Аргументы" value={activity.details} />
						) : null}
						{activity.result ? (
							<ActivityCode label="Результат" value={activity.result} />
						) : null}
					</details>
				</li>
			))}
		</ol>
	);
}

function ActivityCode({ label, value }: { label: string; value: string }) {
	return (
		<div className="mt-3">
			<p className="text-muted-foreground mb-1 text-[9px] font-medium uppercase tracking-wide">
				{label}
			</p>
			<pre className="max-h-56 overflow-auto rounded-lg bg-muted/70 p-2.5 text-[10px] leading-4 whitespace-pre-wrap break-words">
				{value}
			</pre>
		</div>
	);
}

function ConversationView({
	activities,
	detail,
}: {
	activities: readonly AgentTaskActivity[];
	detail: AgentOperationDetail | null;
}) {
	const liveMessages = activities.filter(
		(activity) => activity.kind === "message" && activity.content.trim(),
	);
	const savedTexts = new Set(
		detail?.messages.map((message) => message.text.trim()) ?? [],
	);
	return (
		<div className="space-y-3" aria-label="Диалог задачи">
			{detail?.messages.map((message) => (
				<article
					key={message.id}
					className={cn(
						"max-w-[88%] rounded-2xl px-3 py-2.5 text-[12px] leading-5",
						message.role === "user"
							? "ml-auto bg-blue-600 text-white"
							: "border bg-background",
					)}
				>
					<p className="whitespace-pre-wrap">{message.text}</p>
					<time
						className={cn(
							"mt-1 block text-[9px]",
							message.role === "user"
								? "text-blue-100"
								: "text-muted-foreground",
						)}
					>
						{formatTime(message.createdAt)}
					</time>
				</article>
			))}
			{liveMessages
				.filter((message) => !savedTexts.has(message.content.trim()))
				.map((message) => (
					<article
						key={message.id}
						className="max-w-[88%] rounded-2xl border bg-background px-3 py-2.5 text-[12px] leading-5"
					>
						<p className="whitespace-pre-wrap">{message.content}</p>
					</article>
				))}
			{!detail?.messages.length && !liveMessages.length ? (
				<p className="text-muted-foreground text-[12px]">
					Сообщения задачи ещё не сохранены.
				</p>
			) : null}
		</div>
	);
}

function OperationDetails({ operation }: { operation: AgentOperation }) {
	const policy = operation.frozenPolicy;
	const dispatch = operation.dispatch;
	return (
		<dl className="grid gap-x-5 gap-y-4 text-[11px] sm:grid-cols-2 xl:grid-cols-3">
			<AdminDatum
				label="Runtime profile"
				value={operation.agent.selectedProfile}
			/>
			<AdminDatum label="Tenant" value={operation.task.tenantId} />
			<AdminDatum label="Project" value={operation.task.projectId} />
			<AdminDatum label="Thread" value={operation.task.threadId} />
			<AdminDatum label="События" value={String(operation.lastEventSequence)} />
			<AdminDatum
				label="Последняя активность"
				value={formatTime(operation.timestamps.heartbeatAt)}
			/>
			<AdminDatum
				label="Политика"
				value={
					policy
						? `${policy.sandboxProfile} · approval=${policy.approvalPolicy}`
						: "Не зафиксирована"
				}
			/>
			<AdminDatum
				label="Контур"
				value={
					policy ? `${policy.executionPlane} · ${policy.executionMode}` : "—"
				}
			/>
			<AdminDatum
				label="Очередь"
				value={
					dispatch
						? `${dispatch.state} · ${dispatch.attempts}/${dispatch.maxAttempts}`
						: "Без команды"
				}
			/>
			<AdminDatum
				label="Модель"
				value={
					policy?.modelIdRedacted ? "Скрыта" : (policy?.modelId ?? "По профилю")
				}
			/>
			<AdminDatum
				label="Результат"
				value={
					operation.outcome ??
					operation.errorCode ??
					(operation.errorRedacted ? "Ошибка скрыта" : "—")
				}
			/>
		</dl>
	);
}

"use client";

import { useAuiState, useMessageTiming } from "@assistant-ui/react";
import {
	BrainIcon,
	CheckCircle2Icon,
	ChevronDownIcon,
	CircleXIcon,
	FileCode2Icon,
	LoaderCircleIcon,
	SearchIcon,
	TerminalSquareIcon,
} from "lucide-react";
import { useMemo } from "react";
import {
	buildAgentRun,
	formatAgentElapsed,
	type AgentStep,
} from "@/lib/agent-run";

const isRecord = (value: unknown): value is Record<string, unknown> =>
	typeof value === "object" && value !== null && !Array.isArray(value);

function StepIcon({ step }: { step: AgentStep }) {
	if (step.status === "running") {
		return <LoaderCircleIcon className="size-3.5 shrink-0 animate-spin" aria-hidden="true" />;
	}
	if (step.status === "error") {
		return <CircleXIcon className="size-3.5 shrink-0 text-red-600" aria-hidden="true" />;
	}
	if (step.type === "thinking") {
		return <BrainIcon className="size-3.5 shrink-0" aria-hidden="true" />;
	}
	if (step.type === "tool") {
		const toolName =
			isRecord(step.input) &&
			typeof step.raw === "object" &&
			step.raw !== null &&
			"toolName" in step.raw &&
			typeof step.raw.toolName === "string"
				? step.raw.toolName
				: "";
		if (toolName === "developer_command") {
			return <TerminalSquareIcon className="size-3.5 shrink-0" aria-hidden="true" />;
		}
		if (toolName === "developer_file_change") {
			return <FileCode2Icon className="size-3.5 shrink-0" aria-hidden="true" />;
		}
		if (toolName.includes("search")) {
			return <SearchIcon className="size-3.5 shrink-0" aria-hidden="true" />;
		}
		return <CheckCircle2Icon className="size-3.5 shrink-0 text-emerald-600" aria-hidden="true" />;
	}
	return <CheckCircle2Icon className="size-3.5 shrink-0 text-emerald-600" aria-hidden="true" />;
}

function ToolDetails({ step }: { step: AgentStep }) {
	const raw =
		isRecord(step.raw) &&
		typeof step.raw.toolName === "string"
			? step.raw.toolName
			: "";
	if (raw === "developer_command" && isRecord(step.input)) {
		const command = typeof step.input.command === "string" ? step.input.command : "";
		return command ? (
			<pre className="max-h-48 overflow-auto text-[11px] whitespace-pre-wrap">
				{command}
			</pre>
		) : null;
	}
	if (raw === "developer_file_change" && isRecord(step.input)) {
		const files = Array.isArray(step.input.files)
			? step.input.files.filter(isRecord)
			: [];
		return files.length > 0 ? (
			<div className="space-y-1">
				{files.slice(0, 20).map((file, index) => (
					<div className="text-[11px]" key={`${index}:${String(file.path ?? index)}`}>
						{typeof file.kind === "string" ? `${file.kind}: ` : ""}
						{typeof file.path === "string" ? file.path : "файл"}
					</div>
				))}
			</div>
		) : null;
	}
	return null;
}

function ToolOutput({ step }: { step: AgentStep }) {
	if (!isRecord(step.output)) return null;
	const output = step.output.output;
	if (typeof output !== "string" || !output) return null;
	return (
		<pre className="max-h-48 overflow-auto text-[11px] whitespace-pre-wrap">
			{output.slice(0, 4000)}
		</pre>
	);
}

function StepDetails({ step }: { step: AgentStep }) {
	return (
		<div className="space-y-2">
			{step.type === "tool" ? (
				<div className="space-y-2">
					<ToolDetails step={step} />
					<ToolOutput step={step} />
				</div>
			) : null}
			<details className="group/tech rounded-md border border-border/60 bg-background/60">
				<summary className="text-muted-foreground hover:text-foreground flex cursor-pointer list-none items-center gap-1.5 px-2.5 py-1.5 text-[11px] transition-colors [&::-webkit-details-marker]:hidden">
					Технические данные
					<ChevronDownIcon
						className="size-3 transition-transform group-open/tech:rotate-180"
						aria-hidden="true"
					/>
				</summary>
				<pre className="max-h-64 overflow-auto border-t border-border/60 px-2.5 py-2 text-[10px] whitespace-pre-wrap">
					{JSON.stringify(step.raw, null, 2)}
				</pre>
			</details>
		</div>
	);
}

function AgentRunStep({ step }: { step: AgentStep }) {
	const open = step.status === "running" || step.status === "error";
	return (
		<details
			className="border-border/70 bg-muted/20 rounded-lg border"
			data-slot="agent-run-step"
			open={open || undefined}
		>
			<summary className="hover:bg-muted/35 flex min-h-9 cursor-pointer list-none items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors [&::-webkit-details-marker]:hidden">
				<StepIcon step={step} />
				<span className="min-w-0 flex-1 truncate">{step.title}</span>
				<span className="text-muted-foreground shrink-0 text-[10px] font-normal">
					{step.status === "running"
						? "выполняется"
						: step.status === "error"
							? "ошибка"
							: "готово"}
				</span>
				<ChevronDownIcon
					className="size-3 shrink-0 transition-transform group-open:rotate-180"
					aria-hidden="true"
				/>
			</summary>
			<div className="space-y-2 border-t border-border/60 px-2.5 py-2">
				<StepDetails step={step} />
			</div>
		</details>
	);
}

export function AgentRunFeed({
	startIndex,
	endIndex,
}: {
	startIndex: number;
	endIndex: number;
}) {
	const content = useAuiState((state) => state.message.content);
	const timing = useMessageTiming();
	const parts = useMemo(
		() => content.slice(startIndex, endIndex + 1),
		[content, startIndex, endIndex],
	);
	const run = useMemo(() => buildAgentRun(parts), [parts]);
	const elapsed =
		timing?.totalStreamTime === undefined
			? ""
			: ` · ${formatAgentElapsed(timing.totalStreamTime)}`;

	const header =
		run.status === "running"
			? `Агент работает${elapsed}`
			: run.status === "error"
				? "Агент завершил с ошибкой"
				: "Агент завершил работу";

	return (
		<div data-slot="agent-run-feed" className="my-2">
			<details
				className="group/run rounded-xl border border-border/70 bg-muted/20"
				open={run.status === "running" || run.status === "error" || undefined}
			>
				<summary className="flex cursor-pointer list-none flex-col gap-0.5 px-3 py-2 [&::-webkit-details-marker]:hidden">
					<span className="flex items-center gap-2 text-sm font-medium">
						{run.status === "running" ? (
							<LoaderCircleIcon className="size-4 animate-spin" aria-hidden="true" />
						) : run.status === "error" ? (
							<CircleXIcon className="size-4 text-red-600" aria-hidden="true" />
						) : (
							<CheckCircle2Icon className="size-4 text-emerald-600" aria-hidden="true" />
						)}
						{header}
					</span>
					<span className="text-muted-foreground pl-6 text-xs">
						{run.lastUsefulState}
						{run.progress ? ` · ${run.progress}` : ""}
					</span>
				</summary>
				<div className="space-y-1.5 border-t border-border/60 p-2">
					{run.steps.map((step) => (
						<AgentRunStep key={step.id} step={step} />
					))}
				</div>
			</details>
		</div>
	);
}

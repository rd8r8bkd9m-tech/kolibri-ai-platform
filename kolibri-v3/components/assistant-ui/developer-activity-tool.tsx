"use client";

import {
	type ToolCallMessagePartComponent,
	useAuiState,
	useMessageTiming,
} from "@assistant-ui/react";
import {
	CheckCircle2Icon,
	ChevronRightIcon,
	CircleXIcon,
	FileCode2Icon,
	LoaderCircleIcon,
	TerminalSquareIcon,
	WrenchIcon,
} from "lucide-react";
import type { ReactNode } from "react";

const isRecord = (value: unknown): value is Record<string, unknown> =>
	typeof value === "object" && value !== null && !Array.isArray(value);

const decodeResult = (value: unknown): Record<string, unknown> | null => {
	if (isRecord(value)) return value;
	if (typeof value !== "string") return null;
	try {
		const decoded = JSON.parse(value) as unknown;
		return isRecord(decoded) ? decoded : null;
	} catch {
		return null;
	}
};

const formatWorkDuration = (milliseconds: number): string => {
	const seconds = Math.max(1, Math.round(milliseconds / 1_000));
	const minutes = Math.floor(seconds / 60);
	const remainder = seconds % 60;
	if (minutes === 0) return `${seconds}с`;
	return remainder === 0 ? `${minutes}м` : `${minutes}м ${remainder}с`;
};

const formatStepCount = (count: number): string => {
	const lastDigit = count % 10;
	const lastTwo = count % 100;
	if (lastTwo >= 11 && lastTwo <= 14) return `${count} шагов`;
	if (lastDigit === 1) return `${count} шаг`;
	if (lastDigit >= 2 && lastDigit <= 4) return `${count} шага`;
	return `${count} шагов`;
};

const isDeveloperToolPart = (part: unknown): boolean =>
	isRecord(part) &&
	part.type === "tool-call" &&
	(part.toolName === "developer_command" ||
		part.toolName === "developer_file_change");

const FILE_STEP_LABELS: Record<
	string,
	{ done: string; running: string }
> = {
	read: { done: "Прочитал файл", running: "Читаю файл" },
	glob: { done: "Выполнил поиск", running: "Ищу" },
	grep: { done: "Выполнил поиск", running: "Ищу" },
	search: { done: "Выполнил поиск", running: "Ищу" },
	write: { done: "Изменён файл", running: "Изменяю файл" },
	edit: { done: "Изменён файл", running: "Изменяю файл" },
	patch: { done: "Изменён файл", running: "Изменяю файл" },
	delete: { done: "Удалён файл", running: "Удаляю файл" },
};

const fileStepLabel = (
	kind: unknown,
	running: boolean,
): string => {
	const key = typeof kind === "string" ? kind : "change";
	const labels = FILE_STEP_LABELS[key] ?? {
		done: "Файлы изменены",
		running: "Изменяю файлы",
	};
	return running ? labels.running : labels.done;
};

export function DeveloperActivityGroup({
	children,
	startIndex,
	endIndex,
}: {
	readonly children?: ReactNode;
	readonly startIndex: number;
	readonly endIndex: number;
}) {
	const content = useAuiState((state) => state.message.content);
	const timing = useMessageTiming();
	const parts = content.slice(startIndex, endIndex + 1);
	const developerGroup = parts.some(isDeveloperToolPart);
	const running = parts.some((part) => {
		const value: unknown = part;
		return (
			isRecord(value) &&
			isRecord(value.status) &&
			value.status.type === "running"
		);
	});
	const duration = timing?.totalStreamTime;

	if (!developerGroup) {
		return (
			<details className="min-w-0 max-w-full">
				<summary className="cursor-pointer select-none text-sm" aria-label="Показать действия агента">
					Действия агента ({endIndex - startIndex + 1})
				</summary>
				<div className="mt-1 space-y-1">{children}</div>
			</details>
		);
	}

	const stepCount = endIndex - startIndex + 1;
	const durationLabel = duration === undefined ? "" : ` ${formatWorkDuration(duration)}`;
	return (
		<details
			className="group/developer-work min-w-0 max-w-full border-b pb-2"
			open={running || undefined}
			data-slot="developer-activity-group"
		>
			<summary className="text-muted-foreground hover:text-foreground flex cursor-pointer list-none items-center gap-2 py-2 text-sm transition-colors [&::-webkit-details-marker]:hidden">
				<WrenchIcon className="size-4 shrink-0" aria-hidden="true" />
				<span>
					{running
						? `Ход работы · ${formatStepCount(stepCount)}`
						: `Ход работы · ${formatStepCount(stepCount)}${durationLabel}`}
				</span>
				<ChevronRightIcon
					className="size-4 shrink-0 transition-transform group-open/developer-work:rotate-90"
					aria-hidden="true"
				/>
			</summary>
			<div
				className="space-y-1.5 pt-1"
				role="log"
				aria-label="Журнал работы агента"
			>
				{children}
			</div>
		</details>
	);
}

type DeveloperCommandArgs = {
	readonly command?: unknown;
	readonly cwd?: unknown;
};

export const DeveloperCommandToolUI: ToolCallMessagePartComponent<
	DeveloperCommandArgs,
	unknown
> = ({ args, result, status }) => {
		const completed = status.type !== "running";
		const decoded = decodeResult(result);
		const failed =
			completed &&
			((typeof decoded?.exitCode === "number" && decoded.exitCode !== 0) ||
				decoded?.status === "failed" ||
				decoded?.status === "error");
		const command =
			typeof args.command === "string" && args.command ? args.command : null;
		const isSearch =
			command !== null &&
			/(^|\s)(rg|grep|find)\s/.test(command);
		const output =
			typeof decoded?.output === "string" && decoded.output
				? decoded.output
				: null;
		return (
			<details
				className="group/developer-tool"
				aria-label="Команда агента-разработчика"
			>
				<summary className="text-muted-foreground hover:text-foreground flex min-h-9 cursor-pointer list-none items-center gap-2 rounded-md px-1 py-1.5 text-sm transition-colors [&::-webkit-details-marker]:hidden">
					{failed ? (
						<CircleXIcon
							className="size-4 shrink-0 text-red-600"
							aria-hidden="true"
						/>
					) : completed ? (
						<CheckCircle2Icon
							className="size-4 shrink-0 text-emerald-600"
							aria-hidden="true"
						/>
					) : (
						<LoaderCircleIcon
							className="size-4 shrink-0 animate-spin"
							aria-hidden="true"
						/>
					)}
					<span className="shrink-0">
						{failed
							? isSearch
								? "Поиск завершился с ошибкой"
								: "Команда завершилась с ошибкой"
							: completed
								? isSearch
									? "Выполнен поиск"
									: "Выполнена команда"
								: isSearch
									? "Ищу"
									: "Выполняется команда"}
					</span>
					{command ? (
						<code className="text-muted-foreground ml-auto min-w-0 truncate text-[10px] font-normal">
							{command}
						</code>
					) : null}
					<ChevronRightIcon
						className="size-4 shrink-0 transition-transform group-open/developer-tool:rotate-90"
						aria-hidden="true"
					/>
				</summary>
				<div className="border-border/60 bg-muted/25 rounded-lg border px-2.5 py-2">
					{command ? (
						<pre className="max-h-72 overflow-auto text-[11px] whitespace-pre-wrap">
							{command}
						</pre>
					) : null}
					{output ? (
						<pre className="border-border/60 mt-2 max-h-72 overflow-auto border-t pt-2 font-mono text-[11px] whitespace-pre-wrap">
							{output}
						</pre>
					) : null}
					<footer className="text-muted-foreground mt-1.5 flex flex-wrap gap-3 text-[11px]">
						<TerminalSquareIcon className="size-3.5" aria-hidden="true" />
						{typeof args.cwd === "string" && args.cwd ? (
							<span>{args.cwd}</span>
						) : null}
						{typeof decoded?.exitCode === "number" ? (
							<span>exit {decoded.exitCode}</span>
						) : null}
						{typeof decoded?.durationMs === "number" ? (
							<span>{Math.round(decoded.durationMs)} мс</span>
						) : null}
						{completed ? (
							<span className={failed ? "ml-auto text-red-600" : "ml-auto text-emerald-600"}>
								{failed ? "Ошибка" : "✓ Успех"}
							</span>
						) : null}
					</footer>
				</div>
			</details>
		);
};

type DeveloperFileChangeArgs = {
	readonly files?: unknown;
};

export const DeveloperFileChangeToolUI: ToolCallMessagePartComponent<
	DeveloperFileChangeArgs,
	unknown
> = ({ args, result, status }) => {
		const decoded = decodeResult(result);
		const rawChanges = Array.isArray(decoded?.changes)
			? decoded.changes
			: Array.isArray(args.files)
				? args.files
				: [];
		const changes = rawChanges.filter(isRecord).slice(0, 40);
		const primaryKind = changes[0]?.kind;
		const runningLabel = fileStepLabel(primaryKind, true);
		const doneLabel = fileStepLabel(primaryKind, false);
		const changesLabel =
			changes.length > 0
				? `${changes.length} ${changes.length === 1 ? "файл" : changes.length < 5 ? "файла" : "файлов"}`
				: "";
		return (
			<details
				className="border-border/70 bg-muted/20 group/developer-tool rounded-lg border"
				aria-label="Изменения файлов агентом-разработчиком"
			>
				<summary className="hover:bg-muted/35 flex min-h-9 cursor-pointer list-none items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors [&::-webkit-details-marker]:hidden">
					{status.type === "running" ? (
						<LoaderCircleIcon
							className="size-3.5 shrink-0 animate-spin"
							aria-hidden="true"
						/>
					) : (
						<CheckCircle2Icon
							className="size-3.5 shrink-0 text-emerald-600"
							aria-hidden="true"
						/>
					)}
					<FileCode2Icon className="size-3.5 shrink-0" aria-hidden="true" />
					<span className="shrink-0">
						{status.type === "running"
							? runningLabel
							: doneLabel}
					</span>
					<span className="text-muted-foreground ml-auto truncate text-[10px] font-normal">
						{changesLabel}
					</span>
					<ChevronRightIcon
						className="size-3.5 shrink-0 transition-transform group-open/developer-tool:rotate-90"
						aria-hidden="true"
					/>
				</summary>
				<div className="border-border/60 space-y-2 border-t px-2.5 py-2">
					{changes.map((change, index) => {
						const path =
							typeof change.path === "string"
								? change.path
								: `file-${index + 1}`;
						const diff = typeof change.diff === "string" ? change.diff : "";
						const label = fileStepLabel(change.kind, status.type === "running");
						return (
							<details
								key={`${path}:${index}`}
								className="border-border/60 bg-background/70 rounded-lg border"
							>
								<summary className="cursor-pointer px-2.5 py-2 text-[11px] font-medium">
									{label}: {path}
								</summary>
								{diff ? (
									<pre className="border-border/60 max-h-72 overflow-auto border-t px-2.5 py-2 text-[10px] whitespace-pre">
										{diff}
									</pre>
								) : null}
							</details>
						);
					})}
				</div>
			</details>
		);
};

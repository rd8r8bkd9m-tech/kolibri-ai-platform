export type AgentStepType = "thinking" | "tool" | "delegation" | "message";
export type AgentStepStatus = "running" | "completed" | "error";

export type AgentStep = {
	id: string;
	type: AgentStepType;
	title: string;
	status: AgentStepStatus;
	progress?: string;
	input?: unknown;
	output?: unknown;
	/** Полный сырой журнал шага (не показывается в основной ленте). */
	raw: unknown;
};

export type AgentRun = {
	id: string;
	status: "running" | "completed" | "error";
	startedAt?: number;
	finishedAt?: number;
	steps: AgentStep[];
	assistantMessageId?: string;
	progress: string;
	lastUsefulState: string;
};

export type PartLike = {
	type: string;
	toolName?: unknown;
	toolCallId?: unknown;
	args?: unknown;
	result?: unknown;
	text?: unknown;
	status?: { type?: unknown };
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
	typeof value === "object" && value !== null && !Array.isArray(value);

const statusFromPart = (part: PartLike): AgentStepStatus => {
	const statusType = part.status?.type;
	if (statusType === "running") return "running";
	if (statusType === "error" || statusType === "failed") return "error";
	return "completed";
};

const fileKind = (args: unknown): string | null => {
	if (!isRecord(args)) return null;
	const files = args.files;
	if (!Array.isArray(files)) return null;
	const first = files[0];
	return isRecord(first) && typeof first.kind === "string" ? first.kind : null;
};

const commandFromArgs = (args: unknown): string => {
	if (!isRecord(args) || typeof args.command !== "string") return "";
	return args.command.length > 80
		? `${args.command.slice(0, 80)}…`
		: args.command;
};

export function humanToolTitle(
	toolName: string,
	args: unknown,
	status: AgentStepStatus,
): string {
	const running = status === "running";
	switch (toolName) {
		case "developer_command": {
			const command = commandFromArgs(args);
			const base = running ? "Выполняю команду" : "Команда выполнена";
			return command ? `${base}: ${command}` : base;
		}
		case "developer_file_change": {
			const kind = fileKind(args);
			if (kind === "read") {
				return running ? "Читаю файлы" : "Прочитал файлы";
			}
			if (kind === "glob" || kind === "grep" || kind === "search") {
				return running ? "Ищу" : "Поиск выполнен";
			}
			if (kind === "write" || kind === "edit" || kind === "patch") {
				return running ? "Изменяю файлы" : "Файлы изменены";
			}
			if (kind === "delete") {
				return running ? "Удаляю файлы" : "Файлы удалены";
			}
			return running ? "Работаю с файлами" : "Файлы обработаны";
		}
		case "search_prices":
			return running ? "Ищу цены" : "Цены найдены";
		case "search_normative":
			return running ? "Ищу нормативы" : "Нормативы найдены";
		case "get_weather":
			return running ? "Проверяю погоду" : "Погода проверена";
		case "generate_image":
			return running ? "Создаю изображение" : "Изображение готово";
		case "present":
			return running ? "Формирую представление" : "Представление готово";
		case "create_estimate_document_pack":
			return running ? "Готовлю документы" : "Документы готовы";
		case "delegate_to_agent":
			return running ? "Передаю задачу агенту" : "Задача передана агенту";
		default:
			return toolName;
	}
}

export function buildAgentRun(
	parts: readonly PartLike[],
	options?: {
		runId?: string;
		startedAt?: number;
		finishedAt?: number;
		assistantMessageId?: string;
	},
): AgentRun {
	const steps: AgentStep[] = parts.map((part, index) => {
		const status = statusFromPart(part);
		if (part.type === "reasoning") {
			return {
				id: `step_reasoning_${index}`,
				type: "thinking",
				title: "Анализирую задачу",
				status,
				raw: part,
			};
		}
		if (part.type === "tool-call") {
			const toolName =
				typeof part.toolName === "string" ? part.toolName : "tool";
			return {
				id:
					typeof part.toolCallId === "string"
						? `step_tool_${part.toolCallId}`
						: `step_tool_${index}`,
				type: "tool",
				title: humanToolTitle(toolName, part.args, status),
				status,
				input: part.args,
				output: part.result,
				raw: part,
			};
		}
		return {
			id: `step_message_${index}`,
			type: "message",
			title: "Сообщение",
			status,
			raw: part,
		};
	});

	const running = steps.some((step) => step.status === "running");
	const failed = steps.some((step) => step.status === "error");
	const activeStep = steps.find((step) => step.status === "running");
	const completedCount = steps.filter(
		(step) => step.status === "completed",
	).length;
	const progress =
		steps.length === 0
			? ""
			: running
				? `${completedCount} из ${steps.length} шагов`
				: `Выполнено шагов: ${steps.length}`;
	const lastUsefulState = running
		? (activeStep?.title ?? "Работаю…")
		: failed
			? "Ошибка"
			: "Готово";

	return {
		id: options?.runId ?? "run",
		status: running ? "running" : failed ? "error" : "completed",
		startedAt: options?.startedAt,
		finishedAt: options?.finishedAt,
		steps,
		assistantMessageId: options?.assistantMessageId,
		progress,
		lastUsefulState,
	};
}

export function formatAgentElapsed(milliseconds: number): string {
	const totalSeconds = Math.max(0, Math.round(milliseconds / 1000));
	const minutes = Math.floor(totalSeconds / 60);
	const seconds = totalSeconds % 60;
	return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

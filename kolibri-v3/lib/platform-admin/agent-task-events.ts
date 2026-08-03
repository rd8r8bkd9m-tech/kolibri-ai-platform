export type AgentTaskEvent = {
	sequence: number;
	type:
		| "RUN_ERROR"
		| "RUN_FINISHED"
		| "RUN_STARTED"
		| "TEXT_MESSAGE_CONTENT"
		| "TEXT_MESSAGE_END"
		| "TEXT_MESSAGE_START"
		| "TOOL_CALL_ARGS"
		| "TOOL_CALL_END"
		| "TOOL_CALL_RESULT"
		| "TOOL_CALL_START";
	[key: string]: unknown;
};

export type AgentTaskActivity = {
	id: string;
	kind: "message" | "status" | "tool";
	title: string;
	content: string;
	details: string;
	result: string;
	sequence: number;
	complete: boolean;
	tone: "failed" | "neutral" | "ready" | "running";
};

const EVENT_TYPES = new Set<AgentTaskEvent["type"]>([
	"RUN_ERROR",
	"RUN_FINISHED",
	"RUN_STARTED",
	"TEXT_MESSAGE_CONTENT",
	"TEXT_MESSAGE_END",
	"TEXT_MESSAGE_START",
	"TOOL_CALL_ARGS",
	"TOOL_CALL_END",
	"TOOL_CALL_RESULT",
	"TOOL_CALL_START",
]);

const text = (value: unknown, maximum = 1_000_000) =>
	typeof value === "string" && value.length <= maximum ? value : null;

export function parseAgentTaskEvent(value: unknown): AgentTaskEvent | null {
	if (typeof value !== "object" || value === null || Array.isArray(value)) {
		return null;
	}
	const candidate = value as Record<string, unknown>;
	if (
		typeof candidate.sequence !== "number" ||
		!Number.isSafeInteger(candidate.sequence) ||
		candidate.sequence < 1 ||
		typeof candidate.type !== "string" ||
		!EVENT_TYPES.has(candidate.type as AgentTaskEvent["type"])
	) {
		return null;
	}
	return candidate as AgentTaskEvent;
}

const append = (current: string, delta: unknown) => {
	const next = text(delta);
	return next === null ? current : current + next;
};

const upsert = (
	activities: Map<string, AgentTaskActivity>,
	order: string[],
	id: string,
	create: () => AgentTaskActivity,
) => {
	const existing = activities.get(id);
	if (existing) return existing;
	const activity = create();
	activities.set(id, activity);
	order.push(id);
	return activity;
};

export function applyAgentTaskEvent(
	activities: Map<string, AgentTaskActivity>,
	order: string[],
	event: AgentTaskEvent,
) {
	if (event.type === "RUN_STARTED") {
		upsert(activities, order, "run:started", () => ({
			id: "run:started",
			kind: "status",
			title: "Задача принята",
			content: "Запуск сохранён и передан агентному контуру.",
			details: "",
			result: "",
			sequence: event.sequence,
			complete: true,
			tone: "running",
		}));
		return false;
	}

	if (event.type === "RUN_FINISHED" || event.type === "RUN_ERROR") {
		const failed = event.type === "RUN_ERROR";
		const id = failed ? "run:error" : "run:finished";
		const message = text(event.message, 10_000);
		upsert(activities, order, id, () => ({
			id,
			kind: "status",
			title: failed ? "Задача завершилась с ошибкой" : "Задача завершена",
			content:
				message ??
				(failed
					? "Агентный контур сохранил ошибку выполнения."
					: "Результат сохранён в рабочем контуре."),
			details: "",
			result: "",
			sequence: event.sequence,
			complete: true,
			tone: failed ? "failed" : "ready",
		}));
		return true;
	}

	if (event.type.startsWith("TEXT_MESSAGE_")) {
		const messageId = text(event.messageId, 192);
		if (messageId === null) return false;
		const id = `message:${messageId}`;
		const activity = upsert(activities, order, id, () => ({
			id,
			kind: "message",
			title: event.role === "user" ? "Сообщение пользователя" : "Ответ агента",
			content: "",
			details: "",
			result: "",
			sequence: event.sequence,
			complete: false,
			tone: "running",
		}));
		activity.sequence = event.sequence;
		if (event.type === "TEXT_MESSAGE_CONTENT") {
			activity.content = append(activity.content, event.delta);
		}
		if (event.type === "TEXT_MESSAGE_END") {
			activity.complete = true;
			activity.tone = "ready";
		}
		return false;
	}

	const toolCallId = text(event.toolCallId, 192);
	if (toolCallId === null) return false;
	const id = `tool:${toolCallId}`;
	const toolName = text(event.toolCallName, 160);
	const activity = upsert(activities, order, id, () => ({
		id,
		kind: "tool",
		title: toolName ? `Инструмент · ${toolName}` : "Вызов инструмента",
		content: "",
		details: "",
		result: "",
		sequence: event.sequence,
		complete: false,
		tone: "running",
	}));
	activity.sequence = event.sequence;
	if (toolName) activity.title = `Инструмент · ${toolName}`;
	if (event.type === "TOOL_CALL_ARGS") {
		activity.details = append(activity.details, event.delta);
	}
	if (event.type === "TOOL_CALL_RESULT") {
		activity.result = append(activity.result, event.content);
	}
	if (event.type === "TOOL_CALL_END") {
		activity.complete = true;
		activity.tone = "ready";
	}
	return false;
}

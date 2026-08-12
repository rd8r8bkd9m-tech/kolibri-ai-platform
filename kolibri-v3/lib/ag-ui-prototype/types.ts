/** AG-UI события, которые транспорт разбирает из SSE. */
export type AGUIEvent =
	| {
			type: "RUN_STARTED";
			threadId: string;
			runId: string;
			[key: string]: unknown;
	  }
	| {
			type: "TEXT_MESSAGE_START";
			messageId: string;
			role: "assistant" | "user" | "tool";
			[key: string]: unknown;
	  }
	| {
			type: "TEXT_MESSAGE_CONTENT";
			messageId: string;
			delta: string;
			[key: string]: unknown;
	  }
	| {
			type: "TEXT_MESSAGE_END";
			messageId: string;
			[key: string]: unknown;
	  }
	| {
			type: "TOOL_CALL_START";
			toolCallId: string;
			toolCallName: string;
			parentMessageId?: string;
			[key: string]: unknown;
	  }
	| {
			type: "TOOL_CALL_ARGS";
			toolCallId: string;
			delta: string;
			[key: string]: unknown;
	  }
	| {
			type: "TOOL_CALL_END";
			toolCallId: string;
			[key: string]: unknown;
	  }
	| {
			type: "RUN_FINISHED";
			threadId: string;
			runId: string;
			[key: string]: unknown;
	  }
	| {
			type: "RUN_ERROR";
			message: string;
			code?: string;
			[key: string]: unknown;
	  };

export type ChatMessageRole = "user" | "assistant" | "system" | "tool";

export type ChatMessage = {
	id: string;
	role: ChatMessageRole;
	content: string;
	status: "streaming" | "completed";
};

export type ToolCallState = {
	id: string;
	name: string;
	arguments: string;
	status: "running" | "completed";
};

export type AgentContext = {
	threadId: string;
	runId: string;
	messages: Array<{
		id: string;
		role: "user" | "assistant" | "system";
		content: string;
	}>;
	agentId?: string;
	model?: string;
};

export type AgentEventHandlers = {
	onEvent: (event: AGUIEvent) => void;
	onError: (error: Error) => void;
	onComplete: () => void;
};

export type AgentTransport = {
	sendMessage(
		input: string,
		context: AgentContext,
		handlers: AgentEventHandlers,
	): Promise<void>;
	cancel(): void;
};

export type A2AAgent = {
	id: string;
	name: string;
	description: string;
	capabilities: string[];
	status: "online" | "offline" | "busy";
};

export type A2ATask = {
	id: string;
	agentId: string;
	prompt: string;
	context: AgentContext;
};

export type A2AEvent =
	| { type: "task.started"; taskId: string }
	| { type: "task.delta"; taskId: string; delta: string }
	| { type: "task.completed"; taskId: string; result: string }
	| { type: "task.failed"; taskId: string; error: string };

export type A2AClient = {
	discoverAgents(): Promise<A2AAgent[]>;
	sendTask(agentId: string, task: A2ATask): Promise<string>;
	subscribeToTask(
		taskId: string,
		handler: (event: A2AEvent) => void,
	): () => void;
};

export function isAGUIEvent(value: unknown): value is AGUIEvent {
	if (!value || typeof value !== "object") return false;
	const event = value as Record<string, unknown>;
	return typeof event.type === "string";
}

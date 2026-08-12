import type {
	AGUIEvent,
	AgentContext,
	AgentEventHandlers,
	AgentTransport,
} from "./types.ts";

/**
 * Mock AG-UI транспорт для прототипа: потоковая генерация, tool call,
 * отмена. Явно отделён от FetchAGUITransport.
 */
export class MockAGUITransport implements AgentTransport {
	private cancelled = false;
	private timer: ReturnType<typeof setTimeout> | null = null;
	private interval: ReturnType<typeof setInterval> | null = null;

	async sendMessage(
		_input: string,
		context: AgentContext,
		handlers: AgentEventHandlers,
	): Promise<void> {
		this.cancelled = false;

		const emit = (event: AGUIEvent) => {
			if (!this.cancelled) handlers.onEvent(event);
		};

		emit({
			type: "RUN_STARTED",
			threadId: context.threadId,
			runId: context.runId,
		});

		const messageId = `message_mock_${Date.now()}`;
		emit({
			type: "TEXT_MESSAGE_START",
			messageId,
			role: "assistant",
		});

		const toolCallId = `tool_mock_${Date.now()}`;
		emit({
			type: "TOOL_CALL_START",
			toolCallId,
			toolCallName: "search_prices",
		});
		emit({
			type: "TOOL_CALL_ARGS",
			toolCallId,
			delta: JSON.stringify({ query: "смета" }),
		});
		emit({ type: "TOOL_CALL_END", toolCallId });

		const answer = "Mock-ответ: смета готова, версия 1.";
		await new Promise<void>((resolve) => {
			let index = 0;
			this.interval = setInterval(() => {
				if (this.cancelled) {
					resolve();
					return;
				}
				if (index >= answer.length) {
					if (this.interval) clearInterval(this.interval);
					resolve();
					return;
				}
				const chunk = answer.slice(index, index + 3);
				index += 3;
				emit({
					type: "TEXT_MESSAGE_CONTENT",
					messageId,
					delta: chunk,
				});
			}, 60);
		});

		if (this.cancelled) return;

		emit({ type: "TEXT_MESSAGE_END", messageId });
		emit({
			type: "RUN_FINISHED",
			threadId: context.threadId,
			runId: context.runId,
		});
		handlers.onComplete();
	}

	cancel(): void {
		this.cancelled = true;
		if (this.timer !== null) clearTimeout(this.timer);
		if (this.interval !== null) clearInterval(this.interval);
		this.timer = null;
		this.interval = null;
	}
}

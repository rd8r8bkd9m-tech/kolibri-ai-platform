import type {
	AGUIEvent,
	AgentContext,
	AgentEventHandlers,
	AgentTransport,
} from "./types.ts";
import { isAGUIEvent } from "./types.ts";

const SSE_BLOCK_SEPARATOR = /\r?\n\r?\n/;
const SSE_LINE_SEPARATOR = /\r?\n/;

function parseSSEBlock(block: string): AGUIEvent | null {
	const dataLines = block
		.split(SSE_LINE_SEPARATOR)
		.filter((line) => line.startsWith("data:"))
		.map((line) => line.slice(5).trimStart());

	if (dataLines.length === 0) return null;

	const payload = dataLines.join("\n");
	if (payload === "[DONE]") return null;

	try {
		const parsed: unknown = JSON.parse(payload);
		if (!isAGUIEvent(parsed)) {
			console.warn("Unknown AG-UI event shape", parsed);
			return null;
		}
		return parsed;
	} catch {
		console.warn("Could not parse AG-UI SSE payload", payload);
		return null;
	}
}

/**
 * Production-ready AG-UI транспорт поверх HTTP fetch + ReadableStream.
 * Endpoint передаётся через конфигурацию, токены — только через getHeaders.
 */
export class FetchAGUITransport implements AgentTransport {
	private controller: AbortController | null = null;
	private readonly endpoint: string;
	private readonly getHeaders?: () => HeadersInit;

	constructor(
		endpoint: string,
		getHeaders?: () => HeadersInit,
	) {
		this.endpoint = endpoint;
		this.getHeaders = getHeaders;
	}

	async sendMessage(
		input: string,
		context: AgentContext,
		handlers: AgentEventHandlers,
	): Promise<void> {
		this.controller = new AbortController();

		const response = await fetch(this.endpoint, {
			method: "POST",
			signal: this.controller.signal,
			headers: {
				Accept: "text/event-stream",
				"Content-Type": "application/json",
				...this.getHeaders?.(),
			},
			body: JSON.stringify({
				threadId: context.threadId,
				runId: context.runId,
				messages: context.messages,
				input,
				agentId: context.agentId,
				model: context.model,
			}),
		});

		if (!response.ok) {
			const errorText = await response.text().catch(() => "");
			throw new Error(`AG-UI request failed: ${response.status} ${errorText}`);
		}

		if (!response.body) {
			throw new Error("AG-UI response does not contain a readable stream");
		}

		const contentType = response.headers.get("content-type") ?? "";
		if (!contentType.includes("text/event-stream")) {
			throw new Error(
				`Expected text/event-stream, received ${contentType || "unknown"}`,
			);
		}

		await this.consumeSSE(response.body, handlers);
	}

	cancel(): void {
		this.controller?.abort();
		this.controller = null;
	}

	private async consumeSSE(
		body: ReadableStream<Uint8Array>,
		handlers: AgentEventHandlers,
	): Promise<void> {
		const reader = body.getReader();
		const decoder = new TextDecoder();
		let buffer = "";

		try {
			while (true) {
				const { value, done } = await reader.read();
				if (done) {
					buffer += decoder.decode();
					break;
				}
				buffer += decoder.decode(value, { stream: true });

				const blocks = buffer.split(SSE_BLOCK_SEPARATOR);
				buffer = blocks.pop() ?? "";

				for (const block of blocks) {
					const event = parseSSEBlock(block);
					if (event) handlers.onEvent(event);
				}
			}

			const finalEvent = parseSSEBlock(buffer);
			if (finalEvent) handlers.onEvent(finalEvent);
			handlers.onComplete();
		} catch (error) {
			if (error instanceof DOMException && error.name === "AbortError") {
				return;
			}
			handlers.onError(
				error instanceof Error ? error : new Error(String(error)),
			);
		} finally {
			reader.releaseLock();
		}
	}
}

export { parseSSEBlock, isAGUIEvent };

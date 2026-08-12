import assert from "node:assert/strict";
import test from "node:test";

import { MockAGUITransport } from "../lib/ag-ui-prototype/mock-transport.ts";
import {
	chatReducer,
	initialChatState,
} from "../lib/ag-ui-prototype/reducer.ts";
import {
	FetchAGUITransport,
	parseSSEBlock,
} from "../lib/ag-ui-prototype/transport.ts";
import { isAGUIEvent } from "../lib/ag-ui-prototype/types.ts";

const encoder = new TextEncoder();

function sseStream(...blocks) {
	return new ReadableStream({
		start(controller) {
			for (const block of blocks) {
				controller.enqueue(encoder.encode(`${block}\n\n`));
			}
			controller.close();
		},
	});
}

test("SSE parser decodes AG-UI events and skips [DONE]", () => {
	const event = parseSSEBlock(
		'data: {"type":"RUN_STARTED","threadId":"t","runId":"r"}',
	);
	assert.deepEqual(event, {
		type: "RUN_STARTED",
		threadId: "t",
		runId: "r",
	});
	assert.equal(parseSSEBlock("data: [DONE]"), null);
	assert.equal(parseSSEBlock("event: ping"), null);
	assert.equal(
		parseSSEBlock(
			'data: {"type":"RUN_STARTED"}\ndata: broken json',
		),
		null,
	);
});

test("isAGUIEvent accepts only objects with a string type", () => {
	assert.equal(isAGUIEvent({ type: "RUN_STARTED" }), true);
	assert.equal(isAGUIEvent({ type: 42 }), false);
	assert.equal(isAGUIEvent("RUN_STARTED"), false);
	assert.equal(isAGUIEvent(null), false);
});

test("FetchAGUITransport consumes SSE and completes", async () => {
	const originalFetch = globalThis.fetch;
	globalThis.fetch = async () =>
		new Response(
			sseStream(
				'data: {"type":"RUN_STARTED","threadId":"t","runId":"r"}',
				'data: {"type":"TEXT_MESSAGE_START","messageId":"m","role":"assistant"}',
				'data: {"type":"TEXT_MESSAGE_CONTENT","messageId":"m","delta":"Привет"}',
				'data: {"type":"TEXT_MESSAGE_END","messageId":"m"}',
				'data: {"type":"RUN_FINISHED","threadId":"t","runId":"r"}',
				"data: [DONE]",
			),
			{ status: 200, headers: { "Content-Type": "text/event-stream" } },
		);

	try {
		const transport = new FetchAGUITransport("/api/agent/run");
		const events = [];
		let completed = false;
		await transport.sendMessage(
			"тест",
			{ threadId: "t", runId: "r", messages: [] },
			{
				onEvent: (event) => events.push(event.type),
				onError: (error) => {
					throw error;
				},
				onComplete: () => {
					completed = true;
				},
			},
		);
		assert.deepEqual(events, [
			"RUN_STARTED",
			"TEXT_MESSAGE_START",
			"TEXT_MESSAGE_CONTENT",
			"TEXT_MESSAGE_END",
			"RUN_FINISHED",
		]);
		assert.equal(completed, true);
	} finally {
		globalThis.fetch = originalFetch;
	}
});

test("FetchAGUITransport rejects non-SSE content type", async () => {
	const originalFetch = globalThis.fetch;
	globalThis.fetch = async () =>
		new Response("ok", {
			status: 200,
			headers: { "Content-Type": "application/json" },
		});

	try {
		const transport = new FetchAGUITransport("/api/agent/run");
		await assert.rejects(
			transport.sendMessage(
				"тест",
				{ threadId: "t", runId: "r", messages: [] },
				{
					onEvent: () => undefined,
					onError: () => undefined,
					onComplete: () => undefined,
				},
			),
			/Expected text\/event-stream/,
		);
	} finally {
		globalThis.fetch = originalFetch;
	}
});

test("FetchAGUITransport reports HTTP errors", async () => {
	const originalFetch = globalThis.fetch;
	globalThis.fetch = async () =>
		new Response("denied", { status: 403, headers: {} });

	try {
		const transport = new FetchAGUITransport("/api/agent/run");
		await assert.rejects(
			transport.sendMessage(
				"тест",
				{ threadId: "t", runId: "r", messages: [] },
				{
					onEvent: () => undefined,
					onError: () => undefined,
					onComplete: () => undefined,
				},
			),
			/AG-UI request failed: 403/,
		);
	} finally {
		globalThis.fetch = originalFetch;
	}
});

test("chatReducer transitions through AG-UI events", () => {
	let state = chatReducer(initialChatState, {
		type: "USER_MESSAGE_ADDED",
		payload: {
			id: "u1",
			role: "user",
			content: "привет",
			status: "completed",
		},
	});
	state = chatReducer(state, {
		type: "AGUI_EVENT_RECEIVED",
		payload: {
			type: "RUN_STARTED",
			threadId: "t",
			runId: "r",
		},
	});
	assert.equal(state.isStreaming, true);
	assert.equal(state.activeRunId, "r");

	state = chatReducer(state, {
		type: "AGUI_EVENT_RECEIVED",
		payload: {
			type: "TEXT_MESSAGE_START",
			messageId: "m1",
			role: "assistant",
		},
	});
	state = chatReducer(state, {
		type: "AGUI_EVENT_RECEIVED",
		payload: {
			type: "TEXT_MESSAGE_CONTENT",
			messageId: "m1",
			delta: "От",
		},
	});
	state = chatReducer(state, {
		type: "AGUI_EVENT_RECEIVED",
		payload: {
			type: "TEXT_MESSAGE_CONTENT",
			messageId: "m1",
			delta: "вет",
		},
	});
	state = chatReducer(state, {
		type: "AGUI_EVENT_RECEIVED",
		payload: { type: "TEXT_MESSAGE_END", messageId: "m1" },
	});
	assert.equal(state.messages.at(-1)?.content, "Ответ");
	assert.equal(state.messages.at(-1)?.status, "completed");

	state = chatReducer(state, {
		type: "AGUI_EVENT_RECEIVED",
		payload: {
			type: "TOOL_CALL_START",
			toolCallId: "tc1",
			toolCallName: "search_prices",
		},
	});
	state = chatReducer(state, {
		type: "AGUI_EVENT_RECEIVED",
		payload: {
			type: "TOOL_CALL_ARGS",
			toolCallId: "tc1",
			delta: "{}",
		},
	});
	state = chatReducer(state, {
		type: "AGUI_EVENT_RECEIVED",
		payload: { type: "TOOL_CALL_END", toolCallId: "tc1" },
	});
	assert.equal(state.activeToolCalls.tc1?.status, "completed");

	state = chatReducer(state, {
		type: "AGUI_EVENT_RECEIVED",
		payload: { type: "RUN_ERROR", message: "boom" },
	});
	assert.equal(state.error, "boom");
	assert.equal(state.isStreaming, false);
});

test("MockAGUITransport streams events and can be cancelled", async () => {
	const transport = new MockAGUITransport();
	const events = [];
	let completed = false;
	const sendPromise = transport.sendMessage(
		"привет",
		{ threadId: "t", runId: "r", messages: [] },
		{
			onEvent: (event) => events.push(event.type),
			onError: () => undefined,
			onComplete: () => {
				completed = true;
			},
		},
	);
	await sendPromise;
	assert.ok(events.includes("RUN_STARTED"));
	assert.ok(events.includes("TOOL_CALL_START"));
	assert.ok(events.includes("TEXT_MESSAGE_CONTENT"));
	assert.ok(events.includes("RUN_FINISHED"));
	assert.equal(completed, true);
});

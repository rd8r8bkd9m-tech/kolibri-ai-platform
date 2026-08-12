"use client";

import { useCallback, useReducer, useRef } from "react";
import { chatReducer, initialChatState } from "./reducer.ts";
import { FetchAGUITransport } from "./transport.ts";
import type { AgentTransport } from "./types.ts";

/**
 * React-хук поверх AG-UI транспорта. Транспорт можно заменить на mock,
 * передав его фабрику через параметр.
 */
export function useAGUIChat(options?: {
	createTransport?: (endpoint: string) => AgentTransport;
}) {
	const [state, dispatch] = useReducer(chatReducer, initialChatState);
	const transportRef = useRef<AgentTransport | null>(null);

	const sendMessage = useCallback(
		async (input: string) => {
			const endpoint =
				typeof process !== "undefined" &&
				typeof process.env !== "undefined"
					? (process.env.NEXT_PUBLIC_AG_UI_ENDPOINT ??
						"/api/agent/run")
					: "/api/agent/run";
			const createTransport =
				options?.createTransport ??
				((url: string) => new FetchAGUITransport(url));

			const threadId = state.threadId;
			const runId = crypto.randomUUID();
			const transport = createTransport(endpoint);
			transportRef.current = transport;

			dispatch({
				type: "USER_MESSAGE_ADDED",
				payload: {
					id: crypto.randomUUID(),
					role: "user",
					content: input,
					status: "completed",
				},
			});

			await transport.sendMessage(
				input,
				{
					threadId,
					runId,
					messages: state.messages.map((message) => ({
						id: message.id,
						role:
							message.role === "assistant" || message.role === "user"
								? message.role
								: "system",
						content: message.content,
					})),
					agentId: state.threadId,
					model: "light",
				},
				{
					onEvent: (event) =>
						dispatch({ type: "AGUI_EVENT_RECEIVED", payload: event }),
					onError: (error) =>
						dispatch({ type: "STREAM_ERROR", payload: error.message }),
					onComplete: () => dispatch({ type: "STREAM_COMPLETED" }),
				},
			);
		},
		[options?.createTransport, state],
	);

	const cancelMessage = useCallback(() => {
		transportRef.current?.cancel();
		dispatch({ type: "STREAM_CANCELLED" });
	}, []);

	return { ...state, sendMessage, cancelMessage };
}

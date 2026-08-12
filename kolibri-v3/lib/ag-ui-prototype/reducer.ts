import type { AGUIEvent, ChatMessage, ToolCallState } from "./types.ts";

export type ChatState = {
	threadId: string;
	messages: ChatMessage[];
	activeRunId: string | null;
	isStreaming: boolean;
	activeToolCalls: Record<string, ToolCallState>;
	error: string | null;
};

export type ChatAction =
	| { type: "USER_MESSAGE_ADDED"; payload: ChatMessage }
	| { type: "AGUI_EVENT_RECEIVED"; payload: AGUIEvent }
	| { type: "STREAM_ERROR"; payload: string }
	| { type: "STREAM_COMPLETED" }
	| { type: "STREAM_CANCELLED" };

export const initialChatState: ChatState = {
	threadId: "thread-new",
	messages: [],
	activeRunId: null,
	isStreaming: false,
	activeToolCalls: {},
	error: null,
};

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
	switch (action.type) {
		case "USER_MESSAGE_ADDED":
			return {
				...state,
				messages: [...state.messages, action.payload],
			};

		case "AGUI_EVENT_RECEIVED": {
			const event = action.payload;
			switch (event.type) {
				case "RUN_STARTED":
					return {
						...state,
						activeRunId: event.runId,
						isStreaming: true,
						error: null,
					};

				case "TEXT_MESSAGE_START":
					return {
						...state,
						messages: [
							...state.messages,
							{
								id: event.messageId,
								role:
									event.role === "assistant" ? "assistant" : "tool",
								content: "",
								status: "streaming",
							},
						],
					};

				case "TEXT_MESSAGE_CONTENT":
					return {
						...state,
						messages: state.messages.map((message) =>
							message.id === event.messageId
								? {
										...message,
										content: message.content + event.delta,
									}
								: message,
						),
					};

				case "TEXT_MESSAGE_END":
					return {
						...state,
						messages: state.messages.map((message) =>
							message.id === event.messageId
								? { ...message, status: "completed" }
								: message,
						),
					};

				case "TOOL_CALL_START":
					return {
						...state,
						activeToolCalls: {
							...state.activeToolCalls,
							[event.toolCallId]: {
								id: event.toolCallId,
								name: event.toolCallName,
								arguments: "",
								status: "running",
							},
						},
					};

				case "TOOL_CALL_ARGS":
					return {
						...state,
						activeToolCalls: {
							...state.activeToolCalls,
							[event.toolCallId]: {
								...state.activeToolCalls[event.toolCallId],
								arguments:
									(state.activeToolCalls[event.toolCallId]?.arguments ??
										"") + event.delta,
							},
						},
					};

				case "TOOL_CALL_END":
					return {
						...state,
						activeToolCalls: {
							...state.activeToolCalls,
							[event.toolCallId]: {
								...state.activeToolCalls[event.toolCallId],
								status: "completed",
							},
						},
					};

				case "RUN_FINISHED":
					return {
						...state,
						activeRunId: null,
						isStreaming: false,
					};

				case "RUN_ERROR":
					return {
						...state,
						activeRunId: null,
						isStreaming: false,
						error: event.message,
					};
			}
			return state;
		}

		case "STREAM_ERROR":
			return {
				...state,
				activeRunId: null,
				isStreaming: false,
				error: action.payload,
			};

		case "STREAM_COMPLETED":
			return { ...state, isStreaming: false };

		case "STREAM_CANCELLED":
			return {
				...state,
				activeRunId: null,
				isStreaming: false,
				activeToolCalls: {},
			};
	}
}

import type { VerifiedArtifact, WorkTraceUpdate } from '../api/types';

export type MessageRole = 'user' | 'assistant';
export type MessageStatus = 'streaming' | 'complete' | 'failed' | 'cancelled';

export interface ConversationMessage {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: string;
  status: MessageStatus;
  responseId?: string;
  trace: WorkTraceUpdate[];
  artifacts: VerifiedArtifact[];
}

export interface ConversationState {
  messages: ConversationMessage[];
  previousResponseId?: string;
  activeAssistantId?: string;
}

export const initialConversationState: ConversationState = { messages: [] };

export type ConversationAction =
  | { type: 'turn.started'; user: ConversationMessage; assistant: ConversationMessage }
  | { type: 'response.created'; messageId: string; responseId: string }
  | { type: 'response.delta'; messageId: string; delta: string }
  | { type: 'response.trace'; messageId: string; update: WorkTraceUpdate }
  | { type: 'response.artifact'; messageId: string; artifact: VerifiedArtifact }
  | { type: 'response.completed'; messageId: string; responseId?: string }
  | { type: 'response.failed'; messageId: string; message: string }
  | { type: 'response.cancelled'; messageId: string }
  | { type: 'conversation.cleared' };

function updateMessage(
  state: ConversationState,
  id: string,
  update: (message: ConversationMessage) => ConversationMessage,
): ConversationState {
  return {
    ...state,
    messages: state.messages.map((message) => (message.id === id ? update(message) : message)),
  };
}

export function conversationReducer(
  state: ConversationState,
  action: ConversationAction,
): ConversationState {
  switch (action.type) {
    case 'turn.started':
      return {
        ...state,
        messages: [...state.messages, action.user, action.assistant],
        activeAssistantId: action.assistant.id,
      };
    case 'response.created':
      return updateMessage(state, action.messageId, (message) => ({
        ...message,
        responseId: action.responseId,
      }));
    case 'response.delta':
      return updateMessage(state, action.messageId, (message) => ({
        ...message,
        content: message.content + action.delta,
      }));
    case 'response.trace':
      return updateMessage(state, action.messageId, (message) => {
        const index = message.trace.findIndex((item) => item.id === action.update.id);
        const trace = [...message.trace];
        if (index >= 0) trace[index] = { ...trace[index], ...action.update };
        else trace.push(action.update);
        return { ...message, trace };
      });
    case 'response.artifact':
      return updateMessage(state, action.messageId, (message) => ({
        ...message,
        artifacts: message.artifacts.some((artifact) => artifact.id === action.artifact.id)
          ? message.artifacts
          : [...message.artifacts, action.artifact],
      }));
    case 'response.completed': {
      const next = updateMessage(state, action.messageId, (message) => ({
        ...message,
        status: 'complete',
        trace: message.trace.map((item) =>
          item.status === 'active' ? { ...item, status: 'complete' } : item,
        ),
      }));
      return {
        ...next,
        previousResponseId:
          action.responseId ??
          next.messages.find((message) => message.id === action.messageId)?.responseId ??
          state.previousResponseId,
        activeAssistantId: undefined,
      };
    }
    case 'response.failed': {
      const next = updateMessage(state, action.messageId, (message) => ({
        ...message,
        content: message.content || action.message,
        status: 'failed',
      }));
      return { ...next, activeAssistantId: undefined };
    }
    case 'response.cancelled': {
      const next = updateMessage(state, action.messageId, (message) => ({
        ...message,
        status: 'cancelled',
        trace: [
          ...message.trace.filter((item) => item.id !== 'cancelled'),
          {
            id: 'cancelled',
            stage: 'cancelled',
            label: 'Остановлено',
            status: 'complete',
          },
        ],
      }));
      return { ...next, activeAssistantId: undefined };
    }
    case 'conversation.cleared':
      return initialConversationState;
    default:
      return state;
  }
}

export function createMessage(role: MessageRole, content: string): ConversationMessage {
  return {
    id: crypto.randomUUID(),
    role,
    content,
    createdAt: new Date().toISOString(),
    status: role === 'assistant' ? 'streaming' : 'complete',
    trace: [],
    artifacts: [],
  };
}

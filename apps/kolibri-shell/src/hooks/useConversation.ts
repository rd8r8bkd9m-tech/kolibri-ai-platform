import { useCallback, useReducer, useRef, useState } from 'react';
import type { KolibriClient } from '../api/types';
import {
  type ConversationState,
  conversationReducer,
  createMessage,
  initialConversationState,
} from '../model/conversation';

export function useConversation(
  client: KolibriClient,
  projectId?: string,
  initialState: ConversationState = initialConversationState,
) {
  const [state, dispatch] = useReducer(conversationReducer, initialState);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const responseIdRef = useRef<string | undefined>(undefined);

  const send = useCallback(
    async (input: string, tools: string[], mode: 'fast' | 'reasoning' = 'fast') => {
      const clean = input.trim();
      if (!clean || busy) return;

      const user = createMessage('user', clean);
      const assistant = createMessage('assistant', '');
      const controller = new AbortController();
      abortRef.current = controller;
      responseIdRef.current = undefined;
      setBusy(true);
      dispatch({ type: 'turn.started', user, assistant });

      try {
        await client.streamResponse(
          {
            input: clean,
            previousResponseId: state.previousResponseId,
            projectId,
            tools,
            mode,
          },
          {
            onCreated(responseId) {
              responseIdRef.current = responseId;
              dispatch({ type: 'response.created', messageId: assistant.id, responseId });
            },
            onTextDelta(delta) {
              dispatch({ type: 'response.delta', messageId: assistant.id, delta });
            },
            onTrace(update) {
              dispatch({ type: 'response.trace', messageId: assistant.id, update });
            },
            onArtifact(artifact) {
              dispatch({ type: 'response.artifact', messageId: assistant.id, artifact });
            },
            onCompleted(responseId) {
              dispatch({ type: 'response.completed', messageId: assistant.id, responseId });
            },
            onFailed(message) {
              dispatch({ type: 'response.failed', messageId: assistant.id, message });
            },
          },
          controller.signal,
        );
      } catch (error) {
        if (controller.signal.aborted) {
          dispatch({ type: 'response.cancelled', messageId: assistant.id });
        } else {
          dispatch({
            type: 'response.failed',
            messageId: assistant.id,
            message:
              error instanceof Error
                ? error.message
                : 'Связь с Kolibri прервалась. Запрос можно повторить.',
          });
        }
      } finally {
        abortRef.current = null;
        responseIdRef.current = undefined;
        setBusy(false);
      }
    },
    [busy, client, projectId, state.previousResponseId],
  );

  const stop = useCallback(async () => {
    abortRef.current?.abort();
    const responseId = responseIdRef.current;
    if (responseId) {
      await client.cancelResponse(responseId).catch(() => undefined);
    }
  }, [client]);

  const clear = useCallback(() => {
    abortRef.current?.abort();
    dispatch({ type: 'conversation.cleared' });
    setBusy(false);
  }, []);

  return { state, busy, send, stop, clear };
}

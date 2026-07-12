import {
  initialShellState,
  replaceEstimateLine,
  shellReducer,
  type ComposerMode,
  type EstimateArtifact,
  type ShellEvent,
} from "@domain/shell";
import type { ShellClient } from "@services/shellClient";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";

export interface SendDraft {
  content: string;
  mode: ComposerMode;
  attachmentNames: string[];
}

export function useShellController(client: ShellClient) {
  const [state, dispatch] = useReducer(shellReducer, initialShellState);
  const [connectionAttempt, setConnectionAttempt] = useState(0);
  const activeSend = useRef<AbortController | null>(null);

  const emit = useCallback((event: ShellEvent) => dispatch(event), []);

  useEffect(() => {
    const controller = new AbortController();
    let disconnect: () => void = () => undefined;
    emit({ type: "runtime.connecting" });
    void client
      .start(emit, controller.signal)
      .then((cleanup) => {
        disconnect = cleanup;
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        emit({
          type: "runtime.unavailable",
          message:
            error instanceof Error
              ? `Не удалось подключиться к Kolibri: ${error.message}`
              : "Не удалось подключиться к Kolibri.",
        });
      });
    return () => {
      controller.abort();
      disconnect();
    };
  }, [client, connectionAttempt, emit]);

  useEffect(() => () => activeSend.current?.abort(), []);

  const retry = useCallback(() => setConnectionAttempt((value) => value + 1), []);

  const send = useCallback(
    async (draft: SendDraft) => {
      const content = draft.content.trim();
      if (!content || state.isSending || state.runtimeStatus !== "ready") return false;
      const id = globalThis.crypto.randomUUID();
      const controller = new AbortController();
      activeSend.current?.abort();
      activeSend.current = controller;
      emit({
        type: "message.added",
        message: {
          id,
          author: "user",
          content,
          sentAt: new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }),
          delivery: "sending",
        },
      });
      emit({ type: "sending", value: true });
      try {
        await client.send(
          {
            content,
            mode: draft.mode,
            attachmentNames: draft.attachmentNames,
            clientMessageId: id,
          },
          emit,
          controller.signal,
        );
        return true;
      } catch (error: unknown) {
        if (!controller.signal.aborted) {
          emit({ type: "message.delivery", id, delivery: "failed" });
          emit({
            type: "notice",
            message:
              error instanceof Error
                ? `Сообщение не отправлено: ${error.message}`
                : "Сообщение не отправлено.",
          });
        }
        return false;
      } finally {
        emit({ type: "sending", value: false });
        if (activeSend.current === controller) activeSend.current = null;
      }
    },
    [client, emit, state.isSending, state.runtimeStatus],
  );

  const updateEstimateLine = useCallback(
    (lineId: string, field: "quantity" | "unitPrice", value: number) => {
      if (!state.estimate || !Number.isFinite(value) || value < 0) return;
      emit({
        type: "estimate.updated",
        estimate: replaceEstimateLine(state.estimate, lineId, { [field]: value }),
      });
    },
    [emit, state.estimate],
  );

  const replaceEstimate = useCallback(
    (estimate: EstimateArtifact) => emit({ type: "estimate.updated", estimate }),
    [emit],
  );

  const setNotice = useCallback(
    (message: string | null) => emit({ type: "notice", message }),
    [emit],
  );

  return { state, retry, send, updateEstimateLine, replaceEstimate, setNotice };
}

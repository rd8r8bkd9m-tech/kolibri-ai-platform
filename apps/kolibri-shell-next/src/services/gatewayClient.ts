import type { SafeWorkTrace, ShellSnapshot, TraceStageState } from "@domain/shell";
import {
  eventFromWire,
  publicEventNames,
  responseFromWire,
  sessionFromWire,
  type PublicEventName,
  type PublicResponseStatus,
  type SafeEdgeEvent,
} from "@services/safeWire";
import type { EmitShellEvent, SendMessageInput, ShellClient } from "@services/shellClient";

const terminalStatuses = new Set<PublicResponseStatus>(["completed", "failed", "cancelled", "incomplete"]);

function idempotencyKey(): string {
  return `shell-${globalThis.crypto.randomUUID()}`;
}

async function checkedJson(response: Response): Promise<unknown> {
  if (!response.ok) throw new Error(`Gateway returned HTTP ${response.status}`);
  return response.json() as Promise<unknown>;
}

function emptySnapshot(sessionId: string, currentProjectId: string | null): ShellSnapshot {
  return {
    project: {
      id: currentProjectId ?? `session:${sessionId}`,
      title: currentProjectId ? "Текущий проект" : "Новый проект",
      location: "",
    },
    messages: [],
    trace: null,
    estimate: null,
    activeResponseId: null,
  };
}

function traceForStatus(responseId: string, status: PublicResponseStatus): SafeWorkTrace {
  const progress: Record<PublicResponseStatus, number> = {
    queued: 0,
    planning: 1,
    running: 2,
    verifying: 4,
    completed: 5,
    failed: 2,
    cancelled: 2,
    incomplete: 3,
  };
  const labels = [
    "Понял задачу",
    "Собрал данные",
    "Сформировал результат",
    "Проверил данные",
    "Подготовил ответ",
  ];
  const completed = progress[status];
  const terminal = terminalStatuses.has(status);
  return {
    id: `trace:${responseId}`,
    status: status === "completed" ? "completed" : "running",
    stages: labels.map((label, index) => {
      let state: TraceStageState = "queued";
      if (index < completed) state = "done";
      else if (index === completed && !terminal) state = "active";
      return { id: `safe-${index}`, label, state };
    }),
    agents: [],
  };
}

function eventTime(): string {
  return new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

function handleSafeEvent(
  event: SafeEdgeEvent,
  responseId: string,
  assistantMessageId: string,
  emit: EmitShellEvent,
): boolean {
  if (event.kind === "text.delta") {
    emit({ type: "message.output.delta", id: assistantMessageId, delta: event.delta, sentAt: eventTime() });
  } else if (event.kind === "status") {
    emit({ type: "trace.updated", trace: traceForStatus(responseId, event.status) });
  } else if (event.kind === "activity") {
    emit({
      type: "trace.updated",
      trace: traceForStatus(responseId, event.activity === "verifying" ? "verifying" : "running"),
    });
  } else if (event.kind === "artifact") {
    emit({ type: "notice", message: `Готов проверенный артефакт: ${event.name}` });
  } else if (event.kind === "terminal") {
    emit({ type: "trace.updated", trace: traceForStatus(responseId, event.status) });
    emit({
      type: "message.output.completed",
      id: assistantMessageId,
      content: event.outputText,
      sentAt: eventTime(),
    });
    emit({ type: "response.active", responseId: null });
    if (event.status !== "completed") {
      emit({ type: "notice", message: `Ответ завершён со статусом: ${event.status}.` });
    }
    return true;
  }
  return false;
}

function streamResponse(
  responseId: string,
  startingAfter: number,
  emit: EmitShellEvent,
  signal: AbortSignal,
): Promise<void> {
  const assistantMessageId = `assistant:${responseId}`;
  return new Promise((resolve, reject) => {
    const url = `/v1/responses/${encodeURIComponent(responseId)}?stream=true&starting_after=${startingAfter}`;
    const stream = new EventSource(url, { withCredentials: true });
    let settled = false;

    const finish = (error?: Error) => {
      if (settled) return;
      settled = true;
      stream.close();
      signal.removeEventListener("abort", onAbort);
      if (error) reject(error);
      else resolve();
    };
    const onAbort = () => finish(new DOMException("Aborted", "AbortError"));
    signal.addEventListener("abort", onAbort, { once: true });

    for (const eventName of publicEventNames) {
      stream.addEventListener(eventName, (message) => {
        try {
          const safeEvent = eventFromWire(eventName as PublicEventName, JSON.parse((message as MessageEvent<string>).data) as unknown);
          if (handleSafeEvent(safeEvent, responseId, assistantMessageId, emit)) finish();
        } catch {
          finish(new Error("Gateway sent an invalid public event"));
        }
      });
    }

    stream.onerror = () => {
      if (stream.readyState === EventSource.CLOSED) finish(new Error("Response event stream closed unexpectedly"));
    };
  });
}

export function createGatewayClient(): ShellClient {
  let currentProjectId: string | null = null;
  let previousResponseId: string | null = null;

  return {
    async start(emit, signal) {
      const response = await fetch("/v1/shell/bootstrap", {
        method: "POST",
        credentials: "include",
        signal,
        headers: { Accept: "application/json" },
      });
      const session = sessionFromWire(await checkedJson(response));
      currentProjectId = session.currentProjectId;
      emit({ type: "snapshot", snapshot: emptySnapshot(session.id, currentProjectId) });
      return () => undefined;
    },

    async send(input: SendMessageInput, emit, signal) {
      if (input.attachmentNames.length > 0) {
        throw new Error("Edge пока не принимает вложения из публичного Shell");
      }
      const body: Record<string, unknown> = {
        model: "kolibri",
        input: input.content,
        stream: false,
        background: true,
        execution_mode: input.mode === "reasoning" ? "deep" : "fast",
      };
      if (currentProjectId) body.project_id = currentProjectId;
      if (previousResponseId) body.previous_response_id = previousResponseId;

      const response = await fetch("/v1/responses", {
        method: "POST",
        credentials: "include",
        signal,
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey(),
        },
        body: JSON.stringify(body),
      });
      const created = responseFromWire(await checkedJson(response));
      previousResponseId = created.id;
      emit({ type: "message.delivery", id: input.clientMessageId, delivery: "sent" });
      emit({ type: "response.active", responseId: created.id });
      emit({ type: "trace.updated", trace: traceForStatus(created.id, created.status) });

      if (terminalStatuses.has(created.status)) {
        emit({
          type: "message.output.completed",
          id: `assistant:${created.id}`,
          content: created.outputText,
          sentAt: eventTime(),
        });
        emit({ type: "response.active", responseId: null });
        return;
      }
      await streamResponse(created.id, created.lastSequence, emit, signal);
    },
  };
}

export const publicEventNames = [
  "response.created",
  "response.status.updated",
  "response.output_text.delta",
  "response.reasoning_summary_text.delta",
  "response.tool.started",
  "response.tool.completed",
  "response.work_summary.updated",
  "response.source.added",
  "response.artifact.ready",
  "response.approval.required",
  "response.verification.updated",
  "response.completed",
  "response.failed",
  "response.cancelled",
  "response.incomplete",
] as const;

export type PublicEventName = (typeof publicEventNames)[number];
export type PublicResponseStatus =
  | "queued"
  | "planning"
  | "running"
  | "verifying"
  | "completed"
  | "failed"
  | "cancelled"
  | "incomplete";

export interface PublicSessionWire {
  id: string;
  currentProjectId: string | null;
}

export interface PublicResponseWire {
  id: string;
  status: PublicResponseStatus;
  outputText: string;
  lastSequence: number;
}

export type SafeEdgeEvent =
  | { kind: "status"; sequence: number; status: PublicResponseStatus }
  | { kind: "text.delta"; sequence: number; delta: string }
  | { kind: "terminal"; sequence: number; status: PublicResponseStatus; outputText: string }
  | { kind: "activity"; sequence: number; activity: "running" | "verifying" }
  | { kind: "artifact"; sequence: number; name: string; locator: string }
  | { kind: "ignored"; sequence: number };

const responseStatuses = new Set<PublicResponseStatus>([
  "queued",
  "planning",
  "running",
  "verifying",
  "completed",
  "failed",
  "cancelled",
  "incomplete",
]);

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "") throw new Error(`Invalid ${field}`);
  return value;
}

function status(value: unknown): PublicResponseStatus {
  if (typeof value !== "string" || !responseStatuses.has(value as PublicResponseStatus)) {
    throw new Error("Invalid response status");
  }
  return value as PublicResponseStatus;
}

function sequence(value: unknown): number {
  if (!Number.isSafeInteger(value) || typeof value !== "number" || value < 1) {
    throw new Error("Invalid event sequence");
  }
  return value;
}

export function sessionFromWire(value: unknown): PublicSessionWire {
  const item = record(value);
  if (!item || item.object !== "public.session" || item.active !== true || item.model !== "kolibri") {
    throw new Error("Invalid public session bootstrap");
  }
  const currentProjectId = item.current_project_id;
  if (currentProjectId !== null && typeof currentProjectId !== "string") {
    throw new Error("Invalid public session project");
  }
  return {
    id: requiredString(item.id, "public session id"),
    currentProjectId,
  };
}

export function responseFromWire(value: unknown): PublicResponseWire {
  const item = record(value);
  if (!item || item.object !== "response" || item.model !== "kolibri") {
    throw new Error("Invalid response envelope");
  }
  const outputText = typeof item.output_text === "string" ? item.output_text : "";
  const lastSequence =
    typeof item.last_sequence === "number" && Number.isSafeInteger(item.last_sequence) && item.last_sequence >= 0
      ? item.last_sequence
      : 0;
  return {
    id: requiredString(item.id, "response id"),
    status: status(item.status),
    outputText,
    lastSequence,
  };
}

export function eventFromWire(eventName: PublicEventName, value: unknown): SafeEdgeEvent {
  const payload = record(value);
  if (!payload || payload.type !== eventName) throw new Error("Mismatched public event type");
  const eventSequence = sequence(payload.sequence);

  if (eventName === "response.output_text.delta") {
    return { kind: "text.delta", sequence: eventSequence, delta: requiredString(payload.delta, "text delta") };
  }

  if (eventName === "response.status.updated") {
    return { kind: "status", sequence: eventSequence, status: status(payload.status) };
  }

  if (
    eventName === "response.completed" ||
    eventName === "response.failed" ||
    eventName === "response.cancelled" ||
    eventName === "response.incomplete"
  ) {
    const response = responseFromWire(payload.response);
    return {
      kind: "terminal",
      sequence: eventSequence,
      status: response.status,
      outputText: response.outputText,
    };
  }

  if (eventName === "response.verification.updated") {
    return { kind: "activity", sequence: eventSequence, activity: "verifying" };
  }

  if (
    eventName === "response.created" ||
    eventName === "response.tool.started" ||
    eventName === "response.tool.completed" ||
    eventName === "response.work_summary.updated"
  ) {
    return { kind: "activity", sequence: eventSequence, activity: "running" };
  }

  if (eventName === "response.artifact.ready") {
    const artifact = record(payload.artifact);
    if (!artifact) throw new Error("Invalid artifact event");
    return {
      kind: "artifact",
      sequence: eventSequence,
      name: requiredString(artifact.name, "artifact name"),
      locator: requiredString(artifact.locator, "artifact locator"),
    };
  }

  return { kind: "ignored", sequence: eventSequence };
}

export type RuntimeStatus = "connecting" | "ready" | "unavailable";
export type ComposerMode = "fast" | "reasoning";
export type DeliveryState = "sending" | "sent" | "failed";
export type TraceStageState = "queued" | "active" | "done";

export interface ProjectSummary {
  id: string;
  title: string;
  location: string;
}

export interface ChatMessage {
  id: string;
  author: "user" | "assistant";
  content: string;
  sentAt: string;
  delivery: DeliveryState;
}

export interface TraceStage {
  id: string;
  label: string;
  state: TraceStageState;
}

export interface TraceAgent {
  id: string;
  label: string;
  stateLabel: string;
  tone: "teal" | "yellow";
  icon: "calculator" | "shield";
}

export interface SafeWorkTrace {
  id: string;
  status: "running" | "completed";
  stages: TraceStage[];
  agents: TraceAgent[];
}

export type EstimateLineKind = "foundation" | "shell" | "roof" | "openings" | "systems";

export interface EstimateLine {
  id: string;
  kind: EstimateLineKind;
  label: string;
  unit: string;
  quantity: number;
  unitPrice: number;
}

export interface EstimateArtifact {
  id: string;
  title: string;
  location: string;
  pricedAt: string;
  sourceSummary: string;
  fileName: string;
  fileSizeLabel: string;
  lines: EstimateLine[];
}

export interface ShellSnapshot {
  project: ProjectSummary;
  messages: ChatMessage[];
  trace: SafeWorkTrace | null;
  estimate: EstimateArtifact | null;
  activeResponseId: string | null;
}

export interface ShellState extends ShellSnapshot {
  runtimeStatus: RuntimeStatus;
  errorMessage: string | null;
  notice: string | null;
  isSending: boolean;
}

export type ShellEvent =
  | { type: "snapshot"; snapshot: ShellSnapshot }
  | { type: "runtime.connecting" }
  | { type: "runtime.ready" }
  | { type: "runtime.unavailable"; message: string }
  | { type: "message.added"; message: ChatMessage }
  | { type: "message.delivery"; id: string; delivery: DeliveryState }
  | { type: "message.output.delta"; id: string; delta: string; sentAt: string }
  | { type: "message.output.completed"; id: string; content: string; sentAt: string }
  | { type: "trace.updated"; trace: SafeWorkTrace }
  | { type: "estimate.updated"; estimate: EstimateArtifact }
  | { type: "response.active"; responseId: string | null }
  | { type: "sending"; value: boolean }
  | { type: "notice"; message: string | null };

const emptyProject: ProjectSummary = {
  id: "project-unavailable",
  title: "Kolibri",
  location: "",
};

export const initialShellState: ShellState = {
  runtimeStatus: "connecting",
  errorMessage: null,
  notice: null,
  isSending: false,
  project: emptyProject,
  messages: [],
  trace: null,
  estimate: null,
  activeResponseId: null,
};

export function shellReducer(state: ShellState, event: ShellEvent): ShellState {
  switch (event.type) {
    case "snapshot":
      return {
        ...state,
        ...event.snapshot,
        runtimeStatus: "ready",
        errorMessage: null,
      };
    case "runtime.ready":
      return { ...state, runtimeStatus: "ready", errorMessage: null };
    case "runtime.connecting":
      return { ...state, runtimeStatus: "connecting", errorMessage: null };
    case "runtime.unavailable":
      return {
        ...state,
        runtimeStatus: "unavailable",
        errorMessage: event.message,
        isSending: false,
      };
    case "message.added":
      return { ...state, messages: [...state.messages, event.message] };
    case "message.delivery":
      return {
        ...state,
        messages: state.messages.map((message) =>
          message.id === event.id ? { ...message, delivery: event.delivery } : message,
        ),
      };
    case "message.output.delta": {
      const existing = state.messages.find((message) => message.id === event.id);
      if (existing) {
        return {
          ...state,
          messages: state.messages.map((message) =>
            message.id === event.id
              ? { ...message, content: `${message.content}${event.delta}`, delivery: "sending" }
              : message,
          ),
        };
      }
      return {
        ...state,
        messages: [
          ...state.messages,
          {
            id: event.id,
            author: "assistant",
            content: event.delta,
            sentAt: event.sentAt,
            delivery: "sending",
          },
        ],
      };
    }
    case "message.output.completed": {
      const existing = state.messages.some((message) => message.id === event.id);
      if (existing) {
        return {
          ...state,
          messages: state.messages.map((message) =>
            message.id === event.id
              ? { ...message, content: event.content || message.content, delivery: "sent" }
              : message,
          ),
        };
      }
      if (!event.content) return state;
      return {
        ...state,
        messages: [
          ...state.messages,
          {
            id: event.id,
            author: "assistant",
            content: event.content,
            sentAt: event.sentAt,
            delivery: "sent",
          },
        ],
      };
    }
    case "trace.updated":
      return { ...state, trace: event.trace };
    case "estimate.updated":
      return { ...state, estimate: event.estimate };
    case "response.active":
      return { ...state, activeResponseId: event.responseId };
    case "sending":
      return { ...state, isSending: event.value };
    case "notice":
      return { ...state, notice: event.message };
  }
}

export function lineTotal(line: EstimateLine): number {
  return Math.round(line.quantity * line.unitPrice);
}

export function estimateTotal(estimate: EstimateArtifact): number {
  return estimate.lines.reduce((total, line) => total + lineTotal(line), 0);
}

export interface EstimateGroup {
  id: string;
  label: string;
  kind: "foundation" | "house" | "systems";
  total: number;
}

export function estimateGroups(estimate: EstimateArtifact): EstimateGroup[] {
  const totalFor = (kinds: EstimateLineKind[]) =>
    estimate.lines
      .filter((line) => kinds.includes(line.kind))
      .reduce((sum, line) => sum + lineTotal(line), 0);

  return [
    { id: "foundation", label: "Фундамент", kind: "foundation", total: totalFor(["foundation"]) },
    { id: "house", label: "Коробка дома", kind: "house", total: totalFor(["shell", "roof"]) },
    {
      id: "systems",
      label: "Инженерные системы",
      kind: "systems",
      total: totalFor(["openings", "systems"]),
    },
  ];
}

export function replaceEstimateLine(
  estimate: EstimateArtifact,
  lineId: string,
  patch: Partial<Pick<EstimateLine, "quantity" | "unitPrice">>,
): EstimateArtifact {
  return {
    ...estimate,
    lines: estimate.lines.map((line) => (line.id === lineId ? { ...line, ...patch } : line)),
  };
}

export const formatMoney = (value: number): string =>
  new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(value);

export const completedStageCount = (trace: SafeWorkTrace): number =>
  trace.stages.filter((stage) => stage.state === "done").length;

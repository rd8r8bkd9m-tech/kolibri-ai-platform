export type ProductThread = {
  id: string;
  projectId: string;
  title: string;
  status: "regular" | "archived";
  pinned: boolean;
  createdAt: string;
  updatedAt: string;
  lastMessageAt: string | null;
};

export type ProductMessage = {
  id: string;
  role: "user" | "assistant";
  content: readonly (
    | { type: "text"; text: string }
    | {
        type: "tool-call";
        toolCallId: string;
        toolName: string;
        args: Record<string, unknown>;
        argsText: string;
        result: Record<string, unknown>;
      }
  )[];
  createdAt: string;
  submittedFeedback: "positive" | "negative" | null;
};

const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._~-]{7,127}$/;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isTimestamp = (value: unknown): value is string =>
  typeof value === "string" &&
  value.length <= 64 &&
  Number.isFinite(Date.parse(value));

const isId = (value: unknown): value is string =>
  typeof value === "string" && SAFE_ID.test(value);

const parseThread = (value: unknown): ProductThread => {
  if (
    !isRecord(value) ||
    !isId(value.id) ||
    !isId(value.projectId) ||
    typeof value.title !== "string" ||
    !value.title.trim() ||
    value.title.length > 240 ||
    (value.status !== "regular" && value.status !== "archived") ||
    typeof value.pinned !== "boolean" ||
    !isTimestamp(value.createdAt) ||
    !isTimestamp(value.updatedAt) ||
    (value.lastMessageAt !== null && !isTimestamp(value.lastMessageAt))
  ) {
    throw new Error("Product Chat returned an invalid thread.");
  }
  return {
    id: value.id,
    projectId: value.projectId,
    title: value.title,
    status: value.status,
    pinned: value.pinned,
    createdAt: value.createdAt,
    updatedAt: value.updatedAt,
    lastMessageAt: value.lastMessageAt,
  };
};

const parseContent = (value: unknown): ProductMessage["content"][number] => {
  if (!isRecord(value)) {
    throw new Error("Product Chat returned invalid message content.");
  }
  if (
    value.type === "text" &&
    typeof value.text === "string" &&
    value.text.length <= 1_000_000
  ) {
    return { type: "text", text: value.text };
  }
  if (
    value.type === "tool-call" &&
    isId(value.toolCallId) &&
    typeof value.toolName === "string" &&
    /^[A-Za-z][A-Za-z0-9_-]{0,95}$/.test(value.toolName) &&
    isRecord(value.args) &&
    typeof value.argsText === "string" &&
    value.argsText.length <= 100_000 &&
    isRecord(value.result)
  ) {
    return {
      type: "tool-call",
      toolCallId: value.toolCallId,
      toolName: value.toolName,
      args: value.args,
      argsText: value.argsText,
      result: value.result,
    };
  }
  throw new Error("Product Chat returned invalid message content.");
};

const parseMessage = (value: unknown): ProductMessage => {
  if (
    !isRecord(value) ||
    !isId(value.id) ||
    (value.role !== "user" && value.role !== "assistant") ||
    !Array.isArray(value.content) ||
    value.content.length === 0 ||
    value.content.length > 128 ||
    !isTimestamp(value.createdAt) ||
    (value.submittedFeedback !== null &&
      value.submittedFeedback !== "positive" &&
      value.submittedFeedback !== "negative")
  ) {
    throw new Error("Product Chat returned an invalid message.");
  }
  return {
    id: value.id,
    role: value.role,
    content: value.content.map(parseContent),
    createdAt: value.createdAt,
    submittedFeedback: value.submittedFeedback,
  };
};

export const parseThreadPage = (value: unknown) => {
  if (
    !isRecord(value) ||
    !Array.isArray(value.threads) ||
    value.threads.length > 500 ||
    value.nextCursor !== null
  ) {
    throw new Error("Product Chat returned an invalid thread page.");
  }
  const threads = value.threads.map(parseThread);
  if (new Set(threads.map(({ id }) => id)).size !== threads.length) {
    throw new Error("Product Chat returned duplicate threads.");
  }
  return threads;
};

export const parseMessagePage = (value: unknown, threadId: string) => {
  if (
    !isRecord(value) ||
    value.threadId !== threadId ||
    !Array.isArray(value.messages) ||
    value.messages.length > 2_000 ||
    value.nextCursor !== null
  ) {
    throw new Error("Product Chat returned an invalid message page.");
  }
  const messages = value.messages.map(parseMessage);
  if (new Set(messages.map(({ id }) => id)).size !== messages.length) {
    throw new Error("Product Chat returned duplicate messages.");
  }
  return messages;
};

export const isSafeProductId = isId;

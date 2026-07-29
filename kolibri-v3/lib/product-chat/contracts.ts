export const KOLIBRI_AGENT_PROFILES = [
  "auto",
  "mimo-code",
  "codex-cli",
] as const;

export type KolibriAgentProfile =
  (typeof KOLIBRI_AGENT_PROFILES)[number];
export type KolibriExecutionMode = "standard" | "developer";
export type KolibriAccessMode = "standard" | "auto" | "full";

export type ProductChatThreadStatus = "regular" | "archived";

export type ProductChatThread = {
  readonly id: string;
  readonly projectId: string;
  readonly title: string;
  readonly status: ProductChatThreadStatus;
  readonly pinned: boolean;
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly lastMessageAt: string | null;
};

export type ProductChatThreadPage = {
  readonly threads: readonly ProductChatThread[];
  readonly nextCursor: null;
};

export type ProductChatTextPart = {
  readonly type: "text";
  readonly text: string;
};

export type ProductChatToolCallPart = {
  readonly type: "tool-call";
  readonly toolCallId: string;
  readonly toolName: string;
  readonly args: Readonly<Record<string, unknown>>;
  readonly argsText: string;
  readonly result: Readonly<Record<string, unknown>>;
};

export type ProductChatContentPart =
  | ProductChatTextPart
  | ProductChatToolCallPart;

export type ProductChatMessage = {
  readonly id: string;
  readonly role: "user" | "assistant";
  readonly content: readonly ProductChatContentPart[];
  readonly createdAt: string;
  readonly status: {
    readonly type: "complete";
    readonly reason: "stop";
  };
  readonly submittedFeedback: "positive" | "negative" | null;
};

export type ProductChatMessagePage = {
  readonly threadId: string;
  readonly messages: readonly ProductChatMessage[];
  readonly nextCursor: null;
};

const RFC3339_TIMESTAMP =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/;
const SAFE_OPAQUE_ID =
  /^[A-Za-z0-9][A-Za-z0-9._~-]{7,127}$/;
const THREAD_KEYS = [
  "id",
  "projectId",
  "title",
  "status",
  "pinned",
  "createdAt",
  "updatedAt",
  "lastMessageAt",
] as const;
const MESSAGE_KEYS = [
  "id",
  "role",
  "content",
  "createdAt",
  "status",
  "submittedFeedback",
] as const;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const hasOnlyKeys = (
  value: Record<string, unknown>,
  allowedKeys: readonly string[],
) => {
  const allowed = new Set(allowedKeys);
  return Object.keys(value).every((key) => allowed.has(key));
};

const hasExactlyKeys = (
  value: Record<string, unknown>,
  expectedKeys: readonly string[],
) =>
  Object.keys(value).length === expectedKeys.length &&
  expectedKeys.every((key) => Object.hasOwn(value, key)) &&
  hasOnlyKeys(value, expectedKeys);

const isTimestamp = (value: unknown): value is string =>
  typeof value === "string" &&
  value.length <= 64 &&
  RFC3339_TIMESTAMP.test(value) &&
  Number.isFinite(Date.parse(value));

export const isSafeProductChatId = (value: unknown): value is string =>
  typeof value === "string" && SAFE_OPAQUE_ID.test(value);

export const isKolibriAgentProfile = (
  value: unknown,
): value is KolibriAgentProfile =>
  typeof value === "string" &&
  (KOLIBRI_AGENT_PROFILES as readonly string[]).includes(value);

export class ProductChatContractError extends Error {
  constructor(message = "Product Chat returned an incompatible response.") {
    super(message);
    this.name = "ProductChatContractError";
  }
}

const parseThread = (value: unknown): ProductChatThread => {
  if (!isRecord(value) || !hasExactlyKeys(value, THREAD_KEYS)) {
    throw new ProductChatContractError("Invalid Product Chat thread.");
  }
  if (
    !isSafeProductChatId(value.id) ||
    !isSafeProductChatId(value.projectId) ||
    typeof value.title !== "string" ||
    value.title.trim().length === 0 ||
    value.title.length > 240 ||
    (value.status !== "regular" && value.status !== "archived") ||
    typeof value.pinned !== "boolean" ||
    !isTimestamp(value.createdAt) ||
    !isTimestamp(value.updatedAt) ||
    (value.lastMessageAt !== null && !isTimestamp(value.lastMessageAt))
  ) {
    throw new ProductChatContractError("Invalid Product Chat thread.");
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

const parseTextPart = (value: unknown): ProductChatTextPart => {
  if (
    !isRecord(value) ||
    !hasExactlyKeys(value, ["type", "text"]) ||
    value.type !== "text" ||
    typeof value.text !== "string" ||
    value.text.length > 1_000_000
  ) {
    throw new ProductChatContractError("Invalid Product Chat message part.");
  }
  return { type: "text", text: value.text };
};

const parseToolCallPart = (value: unknown): ProductChatToolCallPart => {
  if (
    !isRecord(value) ||
    !hasExactlyKeys(value, [
      "type",
      "toolCallId",
      "toolName",
      "args",
      "argsText",
      "result",
    ]) ||
    value.type !== "tool-call" ||
    !isSafeProductChatId(value.toolCallId) ||
    typeof value.toolName !== "string" ||
    !/^[A-Za-z][A-Za-z0-9_-]{0,95}$/.test(value.toolName) ||
    !isRecord(value.args) ||
    typeof value.argsText !== "string" ||
    value.argsText.length < 2 ||
    value.argsText.length > 100_000 ||
    !isRecord(value.result)
  ) {
    throw new ProductChatContractError("Invalid Product Chat tool part.");
  }

  try {
    const parsedArgs = JSON.parse(value.argsText) as unknown;
    if (
      !isRecord(parsedArgs) ||
      JSON.stringify(parsedArgs) !== JSON.stringify(value.args)
    ) {
      throw new ProductChatContractError(
        "Product Chat tool arguments do not match.",
      );
    }
  } catch (error) {
    if (error instanceof ProductChatContractError) throw error;
    throw new ProductChatContractError("Invalid Product Chat tool arguments.");
  }

  return {
    type: "tool-call",
    toolCallId: value.toolCallId,
    toolName: value.toolName,
    args: value.args,
    argsText: value.argsText,
    result: value.result,
  };
};

const parseContentPart = (
  value: unknown,
): ProductChatContentPart => {
  if (isRecord(value) && value.type === "tool-call") {
    return parseToolCallPart(value);
  }
  return parseTextPart(value);
};

const parseMessage = (value: unknown): ProductChatMessage => {
  if (
    !isRecord(value) ||
    !hasExactlyKeys(value, MESSAGE_KEYS) ||
    !isSafeProductChatId(value.id) ||
    (value.role !== "user" && value.role !== "assistant") ||
    !Array.isArray(value.content) ||
    value.content.length === 0 ||
    value.content.length > 128 ||
    !isTimestamp(value.createdAt) ||
    !isRecord(value.status) ||
    !hasExactlyKeys(value.status, ["type", "reason"]) ||
    value.status.type !== "complete" ||
    value.status.reason !== "stop" ||
    (
      value.submittedFeedback !== null &&
      value.submittedFeedback !== "positive" &&
      value.submittedFeedback !== "negative"
    ) ||
    (value.role === "user" && value.submittedFeedback !== null)
  ) {
    throw new ProductChatContractError("Invalid Product Chat message.");
  }

  return {
    id: value.id,
    role: value.role,
    content: value.content.map(parseContentPart),
    createdAt: value.createdAt,
    status: { type: "complete", reason: "stop" },
    submittedFeedback: value.submittedFeedback,
  };
};

const requireUniqueIds = (
  values: readonly { readonly id: string }[],
  label: string,
) => {
  if (new Set(values.map(({ id }) => id)).size !== values.length) {
    throw new ProductChatContractError(
      `Product Chat ${label} contains duplicate identifiers.`,
    );
  }
};

export const parseProductChatThreadPage = (
  value: unknown,
): ProductChatThreadPage => {
  if (
    !isRecord(value) ||
    !hasExactlyKeys(value, ["threads", "nextCursor"]) ||
    !Array.isArray(value.threads) ||
    value.threads.length > 500 ||
    value.nextCursor !== null
  ) {
    throw new ProductChatContractError("Invalid Product Chat thread page.");
  }

  const threads = value.threads.map(parseThread);
  requireUniqueIds(threads, "thread page");
  return { threads, nextCursor: null };
};

export const parseProductChatMessagePage = (
  value: unknown,
  expectedThreadId: string,
): ProductChatMessagePage => {
  if (
    !isSafeProductChatId(expectedThreadId) ||
    !isRecord(value) ||
    !hasExactlyKeys(value, ["threadId", "messages", "nextCursor"]) ||
    value.threadId !== expectedThreadId ||
    !Array.isArray(value.messages) ||
    value.messages.length > 2_000 ||
    value.nextCursor !== null
  ) {
    throw new ProductChatContractError("Invalid Product Chat message page.");
  }

  const messages = value.messages.map(parseMessage);
  requireUniqueIds(messages, "message page");
  return {
    threadId: expectedThreadId,
    messages,
    nextCursor: null,
  };
};

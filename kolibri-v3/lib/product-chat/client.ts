import {
  ProductChatContractError,
  isKolibriAgentProfile,
  isSafeProductChatId,
  parseProductChatMessagePage,
  parseProductChatThreadPage,
  type KolibriAgentProfile,
  type KolibriAccessMode,
  type KolibriExecutionMode,
} from "./contracts";
import { withCsrfHeader } from "@/lib/csrf";
import { announceAuthenticationRequired } from "@/lib/identity/events";

export const PRODUCT_CHAT_BFF_BASE = "/api/v3/chat";
export const PRODUCT_AG_UI_BFF_URL = "/api/agui";

const MAX_JSON_RESPONSE_BYTES = 2 * 1_024 * 1_024;
const MAX_AG_UI_REQUEST_BYTES = 2 * 1_024 * 1_024;
const SAFE_SHORT_RUN_ID = /^[A-Za-z0-9][A-Za-z0-9._~-]{0,123}$/;
const defaultFetch: typeof fetch = (...args) => globalThis.fetch(...args);

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const normalizeOpaqueId = (
  value: unknown,
  prefix: "run_" | "msg_" | "tool_",
): string | null => {
  if (isSafeProductChatId(value)) return value;
  if (typeof value !== "string" || !SAFE_SHORT_RUN_ID.test(value)) return null;
  const normalized = `${prefix}${value}`;
  return isSafeProductChatId(normalized) ? normalized : null;
};

type NormalizedAgUiMessage = {
  readonly id: string;
  readonly role: "user";
  readonly content:
    | string
    | Array<
        | { type: "text"; text: string }
        | {
            type: "image" | "document";
            source: {
              type: "url";
              value: string;
              mimeType: string;
            };
            metadata: { filename: string };
          }
      >;
};

const ATTACHMENT_CONTENT_PATH =
  /^\/api\/product\/v1\/attachments\/attachment_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}\/content$/;
const MIME_TYPE =
  /^[a-z0-9][a-z0-9!#$&^_.+-]{0,126}\/[a-z0-9][a-z0-9!#$&^_.+-]{0,126}$/;

const normalizeAttachmentUrl = (value: string): string | null => {
  if (ATTACHMENT_CONTENT_PATH.test(value)) return value;
  if (typeof globalThis.location?.origin !== "string") return null;
  try {
    const parsed = new URL(value);
    if (
      parsed.origin !== globalThis.location.origin ||
      parsed.search ||
      parsed.hash ||
      !ATTACHMENT_CONTENT_PATH.test(parsed.pathname)
    ) {
      return null;
    }
    return parsed.pathname;
  } catch {
    return null;
  }
};

const normalizeAgUiContentPart = (
  value: unknown,
):
  | { type: "text"; text: string }
  | {
      type: "image" | "document";
      source: {
        type: "url";
        value: string;
        mimeType: string;
      };
      metadata: { filename: string };
    }
  | null => {
  if (!isRecord(value)) return null;
  if (
    value.type === "text" &&
    typeof value.text === "string" &&
    value.text.trim()
  ) {
    return { type: "text", text: value.text };
  }
  if (
    (value.type !== "image" && value.type !== "document") ||
    !isRecord(value.source) ||
    value.source.type !== "url" ||
    typeof value.source.value !== "string" ||
    typeof value.source.mimeType !== "string" ||
    !MIME_TYPE.test(value.source.mimeType) ||
    !isRecord(value.metadata) ||
    typeof value.metadata.filename !== "string" ||
    value.metadata.filename.length < 1 ||
    value.metadata.filename.length > 240 ||
    /[/\\\0\r\n]/.test(value.metadata.filename) ||
    (value.type === "image") !==
      value.source.mimeType.startsWith("image/")
  ) {
    return null;
  }
  const contentPath = normalizeAttachmentUrl(value.source.value);
  if (!contentPath) return null;
  return {
    type: value.type,
    source: {
      type: "url",
      value: contentPath,
      mimeType: value.source.mimeType,
    },
    metadata: { filename: value.metadata.filename },
  };
};

const normalizeAgUiMessages = (
  value: unknown,
): NormalizedAgUiMessage[] | null => {
  if (!Array.isArray(value)) return null;

  // Product/Data owns canonical thread history. The browser contributes only
  // the user message that triggered this run. This also covers assistant-ui's
  // legitimate reload shape, where a persisted assistant/tool tail can follow
  // that user message.
  for (let index = value.length - 1; index >= 0; index -= 1) {
    const raw = value[index];
    if (!isRecord(raw) || raw.role !== "user") continue;
    const id = normalizeOpaqueId(raw.id, "msg_");
    if (id === null) return null;
    if (typeof raw.content === "string") {
      if (!raw.content.trim()) return null;
      return [{
        id,
        role: "user",
        content: raw.content,
      }];
    }
    if (!Array.isArray(raw.content)) return null;
    const content = raw.content.map(normalizeAgUiContentPart);
    if (
      content.some((part) => part === null) ||
      !content.some((part) => part?.type === "text") ||
      content.filter((part) => part?.type !== "text").length > 10
    ) {
      return null;
    }
    const normalizedContent = content.filter(
      (part): part is NonNullable<typeof part> => part !== null,
    );
    return [{ id, role: "user", content: normalizedContent }];
  }
  return null;
};

export class ProductChatRequestError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ProductChatRequestError";
    this.status = status;
    this.code = code;
  }
}

const responseError = async (response: Response) => {
  let code = `http_${response.status}`;
  let message = "Не удалось загрузить данные чата.";

  try {
    const value = (await response.clone().json()) as unknown;
    if (isRecord(value)) {
      if (typeof value.code === "string" && value.code.length <= 120) {
        code = value.code;
      }
      if (
        typeof value.message === "string" &&
        value.message.trim().length > 0 &&
        value.message.length <= 500
      ) {
        message = value.message.trim();
      }
    }
  } catch {
    // Raw or malformed upstream details are intentionally not surfaced.
  }

  return new ProductChatRequestError(response.status, code, message);
};

const readBoundedJson = async (response: Response) => {
  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  const declaredLength = Number(response.headers.get("content-length"));
  if (
    !contentType.includes("application/json") ||
    (Number.isFinite(declaredLength) &&
      declaredLength > MAX_JSON_RESPONSE_BYTES)
  ) {
    throw new ProductChatContractError();
  }

  const text = await response.text();
  if (
    new TextEncoder().encode(text).byteLength > MAX_JSON_RESPONSE_BYTES
  ) {
    throw new ProductChatContractError();
  }

  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new ProductChatContractError();
  }
};

export type ProductChatClientOptions = {
  readonly fetch?: typeof fetch;
  readonly baseUrl?: string;
};

export type ProductChatThreadAction =
  | "archive"
  | "unarchive"
  | "pin"
  | "unpin"
  | "remove";
export type ProductChatFeedback = "positive" | "negative";

export class ProductChatClient {
  private readonly fetchImpl: typeof fetch;
  readonly baseUrl: string;

  constructor({
    fetch: fetchImpl = defaultFetch,
    baseUrl = PRODUCT_CHAT_BFF_BASE,
  }: ProductChatClientOptions = {}) {
    if (
      !baseUrl.startsWith("/") ||
      baseUrl.startsWith("//") ||
      baseUrl.includes("\\") ||
      baseUrl.includes("?") ||
      baseUrl.includes("#")
    ) {
      throw new ProductChatContractError(
        "Product Chat client requires a same-origin BFF path.",
      );
    }
    this.fetchImpl = fetchImpl;
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  private async getJson(pathname: string) {
    const response = await this.fetchImpl(`${this.baseUrl}${pathname}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      credentials: "same-origin",
      cache: "no-store",
    });
    if (response.status === 401) announceAuthenticationRequired();
    if (!response.ok) throw await responseError(response);
    return readBoundedJson(response);
  }

  async listThreads() {
    return parseProductChatThreadPage(await this.getJson("/threads")).threads;
  }

  async listMessages(threadId: string) {
    if (!isSafeProductChatId(threadId)) {
      throw new ProductChatContractError("Invalid Product Chat thread ID.");
    }
    const value = await this.getJson(
      `/threads/${encodeURIComponent(threadId)}/messages`,
    );
    return parseProductChatMessagePage(value, threadId);
  }

  async updateThread(
    threadId: string,
    action: ProductChatThreadAction,
  ): Promise<void> {
    if (!isSafeProductChatId(threadId)) {
      throw new ProductChatContractError("Invalid Product Chat thread ID.");
    }
    const headers = withCsrfHeader({
      Accept: "application/json",
      "Content-Type": "application/json",
    });
    const response = await this.fetchImpl(
      `${this.baseUrl}/threads/${encodeURIComponent(threadId)}`,
      {
        method: "PATCH",
        headers,
        credentials: "same-origin",
        cache: "no-store",
        body: JSON.stringify({ action }),
      },
    );
    if (response.status === 401) announceAuthenticationRequired();
    if (!response.ok) throw await responseError(response);
    if (response.status !== 204) {
      throw new ProductChatContractError(
        "Product Chat thread mutation returned an incompatible response.",
      );
    }
  }

  async submitMessageFeedback(
    threadId: string,
    messageId: string,
    type: ProductChatFeedback,
  ): Promise<void> {
    if (
      !isSafeProductChatId(threadId) ||
      !isSafeProductChatId(messageId)
    ) {
      throw new ProductChatContractError(
        "Invalid Product Chat feedback target.",
      );
    }
    const response = await this.fetchImpl(
      `${this.baseUrl}/threads/${encodeURIComponent(threadId)}/messages/${encodeURIComponent(messageId)}/feedback`,
      {
        method: "PUT",
        headers: withCsrfHeader({
          Accept: "application/json",
          "Content-Type": "application/json",
        }),
        credentials: "same-origin",
        cache: "no-store",
        body: JSON.stringify({ type }),
      },
    );
    if (response.status === 401) announceAuthenticationRequired();
    if (!response.ok) throw await responseError(response);
    if (response.status !== 204) {
      throw new ProductChatContractError(
        "Product Chat feedback returned an incompatible response.",
      );
    }
  }

  async cancelRun(runId: string): Promise<void> {
    if (!isSafeProductChatId(runId)) {
      throw new ProductChatContractError("Invalid Product Chat run ID.");
    }
    const response = await this.fetchImpl(
      `${this.baseUrl}/runs/${encodeURIComponent(runId)}/cancel`,
      {
        method: "POST",
        headers: withCsrfHeader({ Accept: "application/json" }),
        credentials: "same-origin",
        cache: "no-store",
      },
    );
    if (response.status === 401) announceAuthenticationRequired();
    if (!response.ok) throw await responseError(response);
    if (response.status !== 204) {
      throw new ProductChatContractError(
        "Product Chat cancellation returned an incompatible response.",
      );
    }
  }
}

const parseAgUiRequestBody = (
  body: BodyInit | null | undefined,
): Record<string, unknown> => {
  if (typeof body !== "string") {
    throw new ProductChatContractError(
      "AG-UI request body must be JSON text.",
    );
  }
  if (new TextEncoder().encode(body).byteLength > MAX_AG_UI_REQUEST_BYTES) {
    throw new ProductChatContractError("AG-UI request is too large.");
  }

  let value: unknown;
  try {
    value = JSON.parse(body) as unknown;
  } catch {
    throw new ProductChatContractError(
      "AG-UI request body must be valid JSON.",
    );
  }

  const normalizedRunId = isRecord(value)
    ? normalizeOpaqueId(value.runId, "run_")
    : null;
  const normalizedMessages = isRecord(value)
    ? normalizeAgUiMessages(value.messages)
    : null;
  const compatible =
    isRecord(value) &&
    isSafeProductChatId(value.threadId) &&
    normalizedRunId !== null &&
    normalizedMessages !== null;
  if (!compatible) {
    throw new ProductChatContractError(
      "AG-UI request has an incompatible shape.",
    );
  }
  return {
    ...(value as Record<string, unknown>),
    runId: normalizedRunId,
    messages: normalizedMessages,
  };
};

export type ProductAgUiFetchOptions = {
  readonly fetch?: typeof fetch;
  readonly getAgentProfile: () => KolibriAgentProfile;
  readonly getExecutionMode: () => KolibriExecutionMode;
  readonly getAccessMode: () => KolibriAccessMode;
  readonly getActiveThreadId: () => string | null;
  readonly onAccepted?: (runId: string) => void | Promise<void>;
};

/**
 * Keeps the browser on the same-origin BFF and replaces all caller-provided
 * forwarded props with the one non-authority preference the backend accepts.
 * Tenant, user, and permission context come only from the HttpOnly session.
 */
export const createProductAgUiFetch = ({
  fetch: fetchImpl = defaultFetch,
  getAgentProfile,
  getExecutionMode,
  getAccessMode,
  getActiveThreadId,
  onAccepted,
}: ProductAgUiFetchOptions): typeof fetch => {
  return async (input, init) => {
    if (typeof input !== "string" || input !== PRODUCT_AG_UI_BFF_URL) {
      throw new ProductChatContractError(
        "AG-UI must use the same-origin Kolibri BFF.",
      );
    }

    const body = parseAgUiRequestBody(init?.body);
    const profile = getAgentProfile();
    if (!isKolibriAgentProfile(profile)) {
      throw new ProductChatContractError("Invalid Kolibri agent profile.");
    }
    const activeThreadId = getActiveThreadId();
    if (!isSafeProductChatId(activeThreadId)) {
      throw new ProductChatContractError(
        "Product Chat requires an active thread.",
      );
    }
    const messages = body.messages as NormalizedAgUiMessage[];
    const executionMode = getExecutionMode();
    if (
      executionMode !== "standard" &&
      executionMode !== "developer"
    ) {
      throw new ProductChatContractError(
        "Invalid Kolibri execution mode.",
      );
    }
    const accessMode = getAccessMode();
    if (
      accessMode !== "standard" &&
      accessMode !== "auto" &&
      accessMode !== "full"
    ) {
      throw new ProductChatContractError(
        "Invalid Kolibri access mode.",
      );
    }
    if (
      (executionMode === "standard") !==
      (accessMode === "standard")
    ) {
      throw new ProductChatContractError(
        "Kolibri execution and access modes are inconsistent.",
      );
    }

    const headers = withCsrfHeader(init?.headers);
    headers.set("Accept", "text/event-stream");
    headers.set("Content-Type", "application/json");

    const response = await fetchImpl(PRODUCT_AG_UI_BFF_URL, {
      ...init,
      method: "POST",
      headers,
      body: JSON.stringify({
        // The official thread-list projection is the browser's current routing
        // choice. HttpAgent can retain the previous ID for one render after
        // ThreadListPrimitive.New; using the synchronous projection prevents
        // a new message from replaying the previous thread's idempotent run.
        // Tenant and project authority are still resolved exclusively by the
        // authenticated backend.
        threadId: activeThreadId,
        runId: body.runId,
        messages,
        // V1 is intentionally text-only. assistant-ui may contribute local
        // instructions, state, context, or tools, but browser-owned authority
        // must never cross into Product Chat until a versioned,
        // server-verified context/tool contract exists.
        state: null,
        tools: [],
        context: [],
        forwardedProps: {
          // Developer mode is a browser request hint, never an authority
          // claim. The backend independently verifies the HttpOnly session,
          // owner role, server feature gate, workspace and sandbox policy.
          // Model/provider choice is independent from the developer access
          // policy: MiMo Code and Codex remain valid in every access mode.
          agentProfile: profile,
          executionMode,
          // Keep ordinary chat on the pre-accessMode V1 wire shape. Developer
          // policies are always explicit: an omitted developer access mode is
          // a locked legacy run and must never be confused with today's
          // bounded automatic-review policy.
          ...(accessMode === "standard" ? {} : { accessMode }),
        },
      }),
      credentials: "same-origin",
      cache: "no-store",
    });

    if (response.status === 401) announceAuthenticationRequired();

    if (response.ok) {
      const mediaType =
        response.headers.get("content-type")?.toLowerCase() ?? "";
      if (
        !response.body ||
        mediaType.split(";", 1)[0]?.trim() !== "text/event-stream"
      ) {
        throw new ProductChatContractError(
          "AG-UI backend did not return an event stream.",
        );
      }
      const acceptedRunId = response.headers.get("x-kolibri-run-id");
      if (!isSafeProductChatId(acceptedRunId)) {
        await response.body.cancel().catch(() => undefined);
        throw new ProductChatContractError(
          "AG-UI backend did not identify the accepted run.",
        );
      }
      try {
        void Promise.resolve(onAccepted?.(acceptedRunId)).catch(
          () => undefined,
        );
      } catch {
        // A projection refresh cannot invalidate an already accepted run.
      }
    }

    return response;
  };
};

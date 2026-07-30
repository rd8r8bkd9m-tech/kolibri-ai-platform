import type {
  Attachment,
  AttachmentAdapter,
  CompleteAttachment,
  PendingAttachment,
} from "@assistant-ui/react";

import { withCsrfHeader } from "@/lib/csrf";
import { announceAuthenticationRequired } from "@/lib/identity/events";

export const PRODUCT_ATTACHMENT_BASE = "/api/product/v1/attachments";
export const PRODUCT_ATTACHMENT_R1_MAX_BYTES = 10 * 1024 * 1024;
const MAX_ATTACHMENT_RESPONSE_BYTES = 64 * 1024;
const ATTACHMENT_ID =
  /^attachment_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$/;
const OPAQUE_ID =
  /^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$/;
const CONTENT_HASH = /^sha256:[0-9a-f]{64}$/;
const MIME_TYPE =
  /^[a-z0-9][a-z0-9!#$&^_.+-]{0,126}\/[a-z0-9][a-z0-9!#$&^_.+-]{0,126}$/;
const CONTENT_PATH =
  /^\/api\/product\/v1\/attachments\/attachment_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}\/content$/;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const hasExactlyKeys = (
  value: Record<string, unknown>,
  keys: readonly string[],
) => {
  const expected = new Set(keys);
  return (
    Object.keys(value).length === keys.length &&
    Object.keys(value).every((key) => expected.has(key))
  );
};

export type ProductAttachmentCapability = {
  readonly enabled: true;
  readonly projectId: string;
  readonly threadId: string;
  readonly canonicalThreadId: string;
  readonly accept: string;
  readonly maxSizeBytes: number;
  readonly maxAttachmentsPerMessage: number;
};

export type ProductAttachmentMetadata = {
  readonly attachmentId: string;
  readonly artifactId: string;
  readonly artifactVersion: number;
  readonly contentHash: string;
  readonly contentPath: string;
  readonly filename: string;
  readonly mimeType: string;
  readonly projectId: string;
  readonly sizeBytes: number;
};

export class ProductAttachmentRequestError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ProductAttachmentRequestError";
    this.status = status;
    this.code = code;
  }
}

const responseError = async (response: Response) => {
  let code = `http_${response.status}`;
  let message = "Не удалось загрузить вложение.";
  try {
    const value = (await response.clone().json()) as unknown;
    if (isRecord(value)) {
      if (typeof value.code === "string" && value.code.length <= 120) {
        code = value.code;
      }
      if (
        typeof value.message === "string" &&
        value.message.length <= 500 &&
        value.message.trim()
      ) {
        message = value.message.trim();
      }
    }
  } catch {
    // Never surface unbounded proxy or upstream details.
  }
  return new ProductAttachmentRequestError(
    response.status,
    code,
    message,
  );
};

const readJson = async (response: Response): Promise<unknown> => {
  const contentType = response.headers.get("content-type") ?? "";
  const declaredLength = Number(response.headers.get("content-length"));
  if (
    !contentType.toLowerCase().includes("application/json") ||
    (Number.isFinite(declaredLength) &&
      declaredLength > MAX_ATTACHMENT_RESPONSE_BYTES)
  ) {
    throw new ProductAttachmentRequestError(
      502,
      "attachment_response_invalid",
      "Backend вернул некорректные данные вложения.",
    );
  }
  const text = await response.text();
  if (
    new TextEncoder().encode(text).byteLength >
    MAX_ATTACHMENT_RESPONSE_BYTES
  ) {
    throw new ProductAttachmentRequestError(
      502,
      "attachment_response_invalid",
      "Backend вернул слишком большой ответ вложения.",
    );
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new ProductAttachmentRequestError(
      502,
      "attachment_response_invalid",
      "Backend вернул некорректные данные вложения.",
    );
  }
};

const parseCapability = (
  value: unknown,
): ProductAttachmentCapability => {
  if (
    !isRecord(value) ||
    !hasExactlyKeys(value, [
      "schemaId",
      "schemaVersion",
      "enabled",
      "projectId",
      "threadId",
      "canonicalThreadId",
      "accept",
      "maxSizeBytes",
      "maxAttachmentsPerMessage",
    ]) ||
    value.schemaId !== "kolibri.product.attachment-capabilities" ||
    value.schemaVersion !== "1.0" ||
    value.enabled !== true ||
    typeof value.projectId !== "string" ||
    !OPAQUE_ID.test(value.projectId) ||
    typeof value.threadId !== "string" ||
    !OPAQUE_ID.test(value.threadId) ||
    typeof value.canonicalThreadId !== "string" ||
    !OPAQUE_ID.test(value.canonicalThreadId) ||
    typeof value.accept !== "string" ||
    value.accept.length < 3 ||
    value.accept.length > 2_000 ||
    value.maxSizeBytes !== PRODUCT_ATTACHMENT_R1_MAX_BYTES ||
    value.maxAttachmentsPerMessage !== 10
  ) {
    throw new ProductAttachmentRequestError(
      502,
      "attachment_capability_invalid",
      "Backend не подтвердил возможность прикреплять файлы.",
    );
  }
  return {
    enabled: true,
    projectId: value.projectId,
    threadId: value.threadId,
    canonicalThreadId: value.canonicalThreadId,
    accept: value.accept,
    maxSizeBytes: value.maxSizeBytes,
    maxAttachmentsPerMessage: value.maxAttachmentsPerMessage,
  };
};

const parseAttachment = (
  value: unknown,
  scope: { projectId: string; attachmentId: string },
): ProductAttachmentMetadata => {
  if (
    !isRecord(value) ||
    !hasExactlyKeys(value, [
      "schema_id",
      "schema_version",
      "tenant_id",
      "user_id",
      "project_id",
      "attachment_id",
      "artifact_id",
      "artifact_version",
      "content_hash",
      "filename",
      "mime_type",
      "size_bytes",
      "content_path",
      "status",
      "created_by",
      "created_at",
    ]) ||
    value.schema_id !== "kolibri.product.attachment" ||
    value.schema_version !== "1.0" ||
    typeof value.tenant_id !== "string" ||
    !OPAQUE_ID.test(value.tenant_id) ||
    typeof value.user_id !== "string" ||
    !OPAQUE_ID.test(value.user_id) ||
    value.project_id !== scope.projectId ||
    value.attachment_id !== scope.attachmentId ||
    typeof value.artifact_id !== "string" ||
    !OPAQUE_ID.test(value.artifact_id) ||
    !Number.isSafeInteger(value.artifact_version) ||
    Number(value.artifact_version) < 1 ||
    typeof value.content_hash !== "string" ||
    !CONTENT_HASH.test(value.content_hash) ||
    typeof value.filename !== "string" ||
    value.filename.length < 1 ||
    value.filename.length > 240 ||
    /[/\\\0\r\n]/.test(value.filename) ||
    typeof value.mime_type !== "string" ||
    !MIME_TYPE.test(value.mime_type) ||
    !Number.isSafeInteger(value.size_bytes) ||
    Number(value.size_bytes) < 1 ||
    Number(value.size_bytes) > PRODUCT_ATTACHMENT_R1_MAX_BYTES ||
    typeof value.content_path !== "string" ||
    !CONTENT_PATH.test(value.content_path) ||
    value.content_path !==
      `${PRODUCT_ATTACHMENT_BASE}/${scope.attachmentId}/content` ||
    value.status !== "available" ||
    typeof value.created_by !== "string" ||
    !OPAQUE_ID.test(value.created_by) ||
    typeof value.created_at !== "string" ||
    !Number.isFinite(Date.parse(value.created_at))
  ) {
    throw new ProductAttachmentRequestError(
      502,
      "attachment_response_invalid",
      "Backend вернул некорректные данные вложения.",
    );
  }
  return {
    attachmentId: value.attachment_id,
    artifactId: value.artifact_id,
    artifactVersion: Number(value.artifact_version),
    contentHash: value.content_hash,
    contentPath: value.content_path,
    filename: value.filename,
    mimeType: value.mime_type,
    projectId: value.project_id,
    sizeBytes: Number(value.size_bytes),
  };
};

export const loadProductAttachmentCapability = async ({
  projectId,
  threadId,
  fetch: fetchImpl = globalThis.fetch,
}: {
  readonly projectId: string;
  readonly threadId: string;
  readonly fetch?: typeof fetch;
}): Promise<ProductAttachmentCapability> => {
  if (!OPAQUE_ID.test(projectId) || !OPAQUE_ID.test(threadId)) {
    throw new ProductAttachmentRequestError(
      404,
      "attachment_scope_not_found",
      "Вложения недоступны для этой задачи.",
    );
  }
  const query = new URLSearchParams({ projectId, threadId });
  const response = await fetchImpl(
    `${PRODUCT_ATTACHMENT_BASE}/capabilities?${query}`,
    {
      method: "GET",
      headers: { Accept: "application/json" },
      credentials: "same-origin",
      cache: "no-store",
    },
  );
  if (response.status === 401) announceAuthenticationRequired();
  if (!response.ok) throw await responseError(response);
  return parseCapability(await readJson(response));
};

const uploadProductAttachment = async ({
  capability,
  file,
  attachmentId,
  fetch: fetchImpl,
}: {
  capability: ProductAttachmentCapability;
  file: File;
  attachmentId: string;
  fetch: typeof fetch;
}) => {
  const response = await fetchImpl(PRODUCT_ATTACHMENT_BASE, {
    method: "POST",
    headers: withCsrfHeader({
      Accept: "application/json",
      "Content-Type": file.type,
      "Idempotency-Key": attachmentId,
      "X-Kolibri-Filename": encodeURIComponent(file.name),
      "X-Kolibri-Project-Id": capability.projectId,
      "X-Kolibri-Thread-Id": capability.threadId,
    }),
    credentials: "same-origin",
    cache: "no-store",
    body: file,
  });
  if (response.status === 401) announceAuthenticationRequired();
  if (!response.ok) throw await responseError(response);
  return parseAttachment(
    await readJson(response),
    { projectId: capability.projectId, attachmentId },
  );
};

export const createProductChatAttachmentAdapter = ({
  capability,
  fetch: fetchImpl = globalThis.fetch,
}: {
  readonly capability: ProductAttachmentCapability;
  readonly fetch?: typeof fetch;
}): AttachmentAdapter => ({
  accept: capability.accept,

  async *add({ file }: { file: File }) {
    const attachmentId =
      `attachment_${globalThis.crypto.randomUUID().replaceAll("-", "")}`;
    const pending: PendingAttachment = {
      id: attachmentId,
      type: file.type.startsWith("image/") ? "image" : "document",
      name: file.name,
      contentType: file.type,
      file,
      status: { type: "running", reason: "uploading", progress: 0 },
    };
    yield pending;
    if (file.size < 1) {
      throw new Error("Нельзя прикрепить пустой файл.");
    }
    if (file.size > capability.maxSizeBytes) {
      throw new Error("Размер вложения превышает лимит 10 МиБ.");
    }

    let metadata: ProductAttachmentMetadata;
    try {
      metadata = await uploadProductAttachment({
        capability,
        file,
        attachmentId,
        fetch: fetchImpl,
      });
    } catch (error) {
      if (
        error instanceof ProductAttachmentRequestError &&
        error.status >= 500
      ) {
        metadata = await uploadProductAttachment({
          capability,
          file,
          attachmentId,
          fetch: fetchImpl,
        });
      } else {
        throw error;
      }
    }

    const absoluteContentUrl = new URL(
      metadata.contentPath,
      globalThis.location.origin,
    ).toString();
    yield {
      ...pending,
      name: metadata.filename,
      contentType: metadata.mimeType,
      content: [
        {
          type: "file",
          data: absoluteContentUrl,
          mimeType: metadata.mimeType,
          filename: metadata.filename,
        },
      ],
      status: { type: "requires-action", reason: "composer-send" },
    };
  },

  async send(
    attachment: PendingAttachment,
  ): Promise<CompleteAttachment> {
    if (!attachment.content?.length) {
      throw new Error("Вложение не было подтверждено backend.");
    }
    return {
      ...attachment,
      content: attachment.content,
      status: { type: "complete" },
    };
  },

  async remove(_attachment: Attachment) {
    // Metadata is immutable and may already be referenced by a retry. Orphan
    // cleanup is a server retention job, never a browser-owned delete.
  },
});

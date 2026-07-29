import type { WorkspaceFile } from "@/components/kolibri-workspace";
import { z } from "zod";

export type WorkspaceCatalogLoadState = "loading" | "ready" | "error";

const documentRecordSchema = z
  .object({
    id: z.string().regex(/^document_[A-Za-z0-9._~-]{8,96}$/),
    projectId: z.string().regex(/^project_[A-Za-z0-9._~-]{8,96}$/),
    projectName: z.string().trim().min(1).max(240),
    category: z.literal("estimates"),
    kind: z.literal("estimate"),
    name: z.string().trim().min(1).max(240),
    status: z.enum(["draft", "ready", "stale", "revoked"]),
    version: z.number().int().min(1),
    updatedAt: z.string().trim().min(1).max(64),
    rowCount: z.number().int().min(0).max(200),
    total: z.string().regex(/^(?:0|[1-9]\d{0,13})(?:\.\d{2})$/),
    currency: z.literal("RUB"),
    editable: z.boolean(),
  })
  .strict();

const documentCatalogSchema = z
  .object({
    documents: z.array(documentRecordSchema).max(500),
  })
  .strict();

const STATUS_LABEL: Record<
  z.infer<typeof documentRecordSchema>["status"],
  WorkspaceFile["status"]
> = {
  draft: "Черновик",
  ready: "Проверен",
  stale: "На согласовании",
  revoked: "Вложение",
};

function formatModifiedAt(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

export function parseWorkspaceDocuments(value: unknown): WorkspaceFile[] {
  const parsed = documentCatalogSchema.safeParse(value);
  if (!parsed.success) {
    throw new Error("Document catalog has an incompatible shape.");
  }
  return parsed.data.documents.map((document) => ({
    category: document.category,
    documentId: document.id,
    editable: document.editable,
    id: document.id,
    kind: document.kind,
    modifiedAt: formatModifiedAt(document.updatedAt),
    name: document.name,
    projectId: document.projectId,
    projectName: document.projectName,
    rowCount: document.rowCount,
    size: `${document.rowCount} поз.`,
    status: STATUS_LABEL[document.status],
    total: document.total,
    version: document.version,
  }));
}

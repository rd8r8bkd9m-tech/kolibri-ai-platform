import type { WorkspaceFile } from "@/lib/workspace-types";
import { z } from "zod";

export type WorkspaceCatalogLoadState = "loading" | "ready" | "error";

const documentStatusSchema = z.enum(["draft", "ready", "stale", "revoked"]);
const documentIdentityFields = {
	id: z.string().regex(/^document_[A-Za-z0-9._~-]{8,96}$/),
	projectId: z.string().regex(/^project_[A-Za-z0-9._~-]{8,96}$/),
	projectName: z.string().trim().min(1).max(240),
	name: z.string().trim().min(1).max(240),
	status: documentStatusSchema,
	version: z.number().int().min(1),
	updatedAt: z.string().trim().min(1).max(64),
};

const estimateDocumentRecordSchema = z
	.object({
		...documentIdentityFields,
		slotType: z.literal("estimate"),
		category: z.literal("estimates"),
		kind: z.literal("estimate"),
		rowCount: z.number().int().min(0),
		total: z.string().regex(/^(?:0|[1-9]\d{0,13})(?:\.\d{2})$/),
		currency: z.literal("RUB"),
		editable: z.boolean(),
	})
	.strict();

const sourceDataDocumentRecordSchema = z
	.object({
		...documentIdentityFields,
		slotType: z.literal("source-data"),
		category: z.literal("documents"),
		kind: z.literal("document"),
		editable: z.literal(false),
	})
	.strict();

const commercialProposalDocumentRecordSchema = z
	.object({
		...documentIdentityFields,
		slotType: z.literal("commercial-proposal"),
		category: z.literal("documents"),
		kind: z.literal("document"),
		editable: z.literal(false),
	})
	.strict();

const contractDocumentRecordSchema = z
	.object({
		...documentIdentityFields,
		slotType: z.literal("contract"),
		category: z.literal("contracts"),
		kind: z.literal("contract"),
		editable: z.literal(false),
	})
	.strict();

const documentRecordSchema = z.discriminatedUnion("slotType", [
	sourceDataDocumentRecordSchema,
	estimateDocumentRecordSchema,
	commercialProposalDocumentRecordSchema,
	contractDocumentRecordSchema,
]);

const documentCatalogSchema = z
	.object({
		documents: z.array(documentRecordSchema).max(500),
	})
	.strict();

const STATUS_LABEL: Record<
	z.infer<typeof documentStatusSchema>,
	WorkspaceFile["status"]
> = {
	draft: "Черновик",
	ready: "Проверен",
	stale: "Устарел",
	revoked: "Отозван",
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
		slotType: document.slotType,
		size:
			document.slotType === "estimate"
				? `${document.rowCount} поз.`
				: `Версия ${document.version}`,
		status: STATUS_LABEL[document.status],
		version: document.version,
		...(document.slotType === "estimate"
			? { rowCount: document.rowCount, total: document.total }
			: {}),
	}));
}

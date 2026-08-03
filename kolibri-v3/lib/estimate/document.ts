import { withCsrfHeader } from "@/lib/csrf";
import { kolibriGenerativeUIComponentSchemas } from "@/lib/generative-ui/schema";
import type { z } from "zod";

export const ESTIMATE_ROW_PAGE_SIZE = 100;
export const ESTIMATE_ROW_MUTATION_BATCH_MAX = 200;

export type EstimateDocument = z.infer<
	typeof kolibriGenerativeUIComponentSchemas.EstimateEditor
>;
export type EstimateRow = EstimateDocument["rows"][number];
export type EditableEstimateRow = Omit<EstimateRow, "lineTotal">;
export type EstimateRowUpsert = Omit<
	EstimateRow,
	"lineTotal" | "priceEvidence" | "enginePriceProvenance"
>;

export type EstimateRowDelta = {
	readonly upsertRows: readonly EstimateRowUpsert[];
	readonly deleteRowIds: readonly string[];
};

type EstimateWindowIdentity = {
	readonly documentId?: string;
	readonly minimumVersion?: number;
	readonly projectId: string;
};

export class EstimateClientError extends Error {
	readonly payload: unknown;
	readonly status: number;

	constructor(status: number, message: string, payload: unknown = null) {
		super(message);
		this.name = "EstimateClientError";
		this.status = status;
		this.payload = payload;
	}
}

const readResponseError = async (response: Response) => {
	try {
		const value = (await response.clone().json()) as unknown;
		if (typeof value !== "object" || value === null) {
			return "Не удалось загрузить смету.";
		}
		const record = value as Record<string, unknown>;
		const detail =
			typeof record.detail === "object" && record.detail !== null
				? (record.detail as Record<string, unknown>)
				: record;
		return typeof detail.message === "string"
			? detail.message
			: "Не удалось загрузить смету.";
	} catch {
		return "Не удалось загрузить смету.";
	}
};

const parseEstimateDocument = (
	value: unknown,
	identity: EstimateWindowIdentity,
): EstimateDocument => {
	const parsed = kolibriGenerativeUIComponentSchemas.EstimateEditor.safeParse(value);
	if (!parsed.success) {
		throw new Error("Сервер вернул смету неизвестного формата.");
	}
	if (
		parsed.data.projectId !== identity.projectId ||
		(identity.documentId !== undefined &&
			parsed.data.documentId !== identity.documentId)
	) {
		throw new Error(
			"Сервер вернул другую смету. Обновите список файлов и откройте документ снова.",
		);
	}
	if (
		identity.minimumVersion !== undefined &&
		parsed.data.version < identity.minimumVersion
	) {
		throw new Error(
			`Сервер вернул версию ${parsed.data.version}, а выбрана версия ${identity.minimumVersion}.`,
		);
	}
	return parsed.data;
};

const normalizeWindow = (offset: number, limit: number) => ({
	offset: Math.max(0, Math.trunc(offset)),
	limit: Math.min(ESTIMATE_ROW_PAGE_SIZE, Math.max(1, Math.trunc(limit))),
});

export const estimateTotalRows = (estimate: EstimateDocument) =>
	estimate.rowPage?.totalRows ?? estimate.rows.length;

export const estimateRowOffset = (estimate: EstimateDocument) =>
	estimate.rowPage?.offset ?? 0;

export async function loadEstimateWindow(
	identity: EstimateWindowIdentity & { readonly offset?: number; readonly limit?: number },
): Promise<EstimateDocument> {
	const window = normalizeWindow(
		identity.offset ?? 0,
		identity.limit ?? ESTIMATE_ROW_PAGE_SIZE,
	);
	const query = new URLSearchParams({
		offset: String(window.offset),
		limit: String(window.limit),
	});
	const response = await fetch(
		`/api/v3/projects/${encodeURIComponent(identity.projectId)}/estimate?${query.toString()}`,
		{
			method: "GET",
			headers: { Accept: "application/json" },
			credentials: "same-origin",
			cache: "no-store",
		},
	);
	if (!response.ok) throw new Error(await readResponseError(response));
	return parseEstimateDocument(await response.json(), identity);
}

export const toEstimateRowUpsert = (
	row: EstimateRow | EditableEstimateRow,
): EstimateRowUpsert => {
	const {
		lineTotal: _lineTotal,
		priceEvidence: _priceEvidence,
		enginePriceProvenance: _enginePriceProvenance,
		...upsert
	} = row as EstimateRow;
	void _lineTotal;
	void _priceEvidence;
	void _enginePriceProvenance;
	return upsert;
};

export function buildEstimateRowDelta(
	baseline: readonly (EstimateRow | EditableEstimateRow)[],
	current: readonly (EstimateRow | EditableEstimateRow)[],
): EstimateRowDelta {
	const baselineById = new Map(
		baseline.map((row) => [row.id, JSON.stringify(toEstimateRowUpsert(row))]),
	);
	const currentIds = new Set(current.map((row) => row.id));
	const upsertRows = current
		.map(toEstimateRowUpsert)
		.filter(
			(row) => baselineById.get(row.id) !== JSON.stringify(row),
		);
	const deleteRowIds = baseline
		.filter((row) => !currentIds.has(row.id))
		.map((row) => row.id);
	return { upsertRows, deleteRowIds };
}

export async function saveEstimateRowDelta(input: {
	readonly baselineRows: readonly (EstimateRow | EditableEstimateRow)[];
	readonly baselineTitle: string;
	readonly estimate: Pick<
		EstimateDocument,
		"documentId" | "projectId" | "version"
	>;
	readonly limit?: number;
	readonly offset?: number;
	readonly rows: readonly (EstimateRow | EditableEstimateRow)[];
	readonly title: string;
}): Promise<EstimateDocument> {
	const window = normalizeWindow(
		input.offset ?? 0,
		input.limit ?? ESTIMATE_ROW_PAGE_SIZE,
	);
	const delta = buildEstimateRowDelta(input.baselineRows, input.rows);
	if (
		delta.upsertRows.length > ESTIMATE_ROW_MUTATION_BATCH_MAX ||
		delta.deleteRowIds.length > ESTIMATE_ROW_MUTATION_BATCH_MAX
	) {
		throw new Error("Слишком много строк изменено за один раз. Сохраните правки частями.");
	}
	const title = input.title.trim();
	if (
		title === input.baselineTitle &&
		delta.upsertRows.length === 0 &&
		delta.deleteRowIds.length === 0
	) {
		return loadEstimateWindow({
			documentId: input.estimate.documentId,
			minimumVersion: input.estimate.version,
			offset: window.offset,
			limit: window.limit,
			projectId: input.estimate.projectId,
		});
	}
	const response = await fetch(
		`/api/v3/projects/${encodeURIComponent(input.estimate.projectId)}/estimate/rows`,
		{
			method: "PATCH",
			headers: withCsrfHeader({
				Accept: "application/json",
				"Content-Type": "application/json",
			}),
			body: JSON.stringify({
				version: input.estimate.version,
				...(title !== input.baselineTitle ? { title } : {}),
				upsertRows: delta.upsertRows,
				deleteRowIds: delta.deleteRowIds,
				returnPage: window,
			}),
			credentials: "same-origin",
			cache: "no-store",
		},
	);
	if (!response.ok) {
		let payload: unknown = null;
		try {
			payload = await response.clone().json();
		} catch {
			// Keep the bounded text fallback for upstream non-JSON errors.
		}
		throw new EstimateClientError(
			response.status,
			await readResponseError(response),
			payload,
		);
	}
	return parseEstimateDocument(await response.json(), {
		documentId: input.estimate.documentId,
		minimumVersion: input.estimate.version + 1,
		projectId: input.estimate.projectId,
	});
}

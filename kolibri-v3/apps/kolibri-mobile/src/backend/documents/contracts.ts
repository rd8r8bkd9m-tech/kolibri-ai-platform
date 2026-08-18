export type DocumentSummary = {
	id: string;
	projectId: string;
	projectName: string;
	slotType: string;
	category: string;
	kind: string;
	name: string;
	status: string;
	version: number;
	updatedAt: string;
	editable: boolean;
	rowCount?: number;
	total?: string;
	currency?: "RUB";
};

const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._~-]{7,127}$/;

const isRecord = (value: unknown): value is Record<string, unknown> =>
	typeof value === "object" && value !== null && !Array.isArray(value);

const isTimestamp = (value: unknown): value is string =>
	typeof value === "string" &&
	value.length <= 64 &&
	Number.isFinite(Date.parse(value));

export const parseDocumentCatalog = (
	value: unknown,
): readonly DocumentSummary[] => {
	if (!isRecord(value) || !Array.isArray(value.documents)) {
		throw new Error("Document catalog is invalid.");
	}
	return value.documents.flatMap((item): DocumentSummary[] => {
		if (
			!isRecord(item) ||
			typeof item.id !== "string" ||
			!SAFE_ID.test(item.id) ||
			typeof item.projectId !== "string" ||
			!SAFE_ID.test(item.projectId) ||
			typeof item.slotType !== "string" ||
			typeof item.category !== "string" ||
			typeof item.kind !== "string" ||
			typeof item.name !== "string" ||
			typeof item.status !== "string" ||
			typeof item.version !== "number" ||
			!Number.isInteger(item.version) ||
			item.version < 1 ||
			typeof item.editable !== "boolean" ||
			!isTimestamp(item.updatedAt) ||
			typeof item.projectName !== "string"
		) {
			return [];
		}
		const result: DocumentSummary = {
			id: item.id,
			projectId: item.projectId,
			projectName: item.projectName,
			slotType: item.slotType,
			category: item.category,
			kind: item.kind,
			name: item.name,
			status: item.status,
			version: item.version,
			updatedAt: item.updatedAt,
			editable: item.editable,
		};
		if (typeof item.rowCount === "number") result.rowCount = item.rowCount;
		if (typeof item.total === "string") result.total = item.total;
		if (item.currency === "RUB") result.currency = item.currency;
		return [result];
	});
};

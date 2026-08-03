const SAFE_PROJECT_ID = /^project_[A-Za-z0-9._~-]{8,96}$/;
const SAFE_DOCUMENT_ID = /^document_[A-Za-z0-9._~-]{8,96}$/;
const SAFE_ROW_ID = /^row_[A-Za-z0-9._~-]{8,96}$/;
const DECIMAL_TEXT = /^(?:0|[1-9]\d{0,11})(?:\.\d{1,6})?$/;
const MONEY_TEXT = /^(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$/;
const TOTAL_TEXT = /^(?:0|[1-9]\d{0,13})(?:\.\d{2})$/;
const CHAT_RUN_ID = /^(?:run|calculation)_[A-Za-z0-9._~-]{8,96}$/;
const PROVIDER_PROFILE = /^[a-z0-9][a-z0-9._-]{1,95}$/;
const SHA256 = /^sha256:[0-9a-f]{64}$/;

export const NATIVE_ESTIMATE_PAGE_SIZE = 100;

const isRecord = (value: unknown): value is Record<string, unknown> =>
	typeof value === "object" && value !== null && !Array.isArray(value);

const isTimestamp = (value: unknown): value is string =>
	typeof value === "string" &&
	value.length <= 64 &&
	Number.isFinite(Date.parse(value));

const readBoundedText = (value: unknown, field: string, maximum: number) => {
	if (
		typeof value !== "string" ||
		value.trim().length === 0 ||
		value.length > maximum
	) {
		throw new Error(`Estimate field ${field} is invalid.`);
	}
	return value;
};

const readOptionalText = (value: unknown, field: string, maximum = 160) =>
	value === undefined ? undefined : readBoundedText(value, field, maximum);

const ROW_KINDS: readonly NativeEstimateRow["kind"][] = [
	"work",
	"material",
	"equipment",
	"service",
	"overhead",
	"tax",
	"contingency",
];

const LINE_CONFIDENCE: readonly NativeEstimateRow["lineConfidence"][] = [
	"missing",
	"preliminary",
	"source_backed",
	"verified",
];

export type EstimateDocumentSummary = {
	id: string;
	projectId: string;
	projectName: string;
	name: string;
	status: string;
	version: number;
	updatedAt: string;
	rowCount: number;
	total: string;
	currency: "RUB";
	editable: boolean;
};

export type NativeEstimateRow = {
	id: string;
	section: string;
	kind:
		| "work"
		| "material"
		| "equipment"
		| "service"
		| "overhead"
		| "tax"
		| "contingency";
	description: string;
	unit: string;
	quantity: string;
	unitPrice: string;
	lineTotal: string;
	quantityBasis: string;
	priceBasis: string;
	operationId?: string;
	technologyCardVersion?: string;
	resourceId?: string;
	evidenceId?: string;
	wbsPath?: string;
	specification?: string;
	quantityFormula?: string;
	catalogEntryId?: string;
	catalogEntryVersion?: number;
	priceObservationId?: string;
	marketAggregateId?: string;
	lineConfidence: "missing" | "preliminary" | "source_backed" | "verified";
};

export type NativeEstimateRowPage = {
	offset: number;
	limit: number;
	totalRows: number;
	hasMore: boolean;
};

export type NativeEstimateGeneration = {
	providerProfile: string;
	runId: string;
	estimateGenerationRunId?: string;
	technologyCardRevisionId?: string;
	technologyCardHash?: string;
	qualityStatus?: "pending" | "failed" | "passed";
};

export type NativeEstimate = {
	schemaId: "kolibri.estimate_draft";
	schemaVersion: "1.2" | "1.3" | "1.4";
	projectId: string;
	documentId: string;
	version: number;
	status: string;
	estimateTitle: string;
	currency: "RUB";
	rows: readonly NativeEstimateRow[];
	rowPage?: NativeEstimateRowPage;
	generation?: NativeEstimateGeneration | null;
	totals: { subtotal: string; total: string };
};

export const parseEstimateCatalog = (
	value: unknown,
): readonly EstimateDocumentSummary[] => {
	if (!isRecord(value) || !Array.isArray(value.documents)) {
		throw new Error("Document catalog is invalid.");
	}
	return value.documents
		.filter(
			(item) =>
				isRecord(item) &&
				item.category === "estimates" &&
				item.kind === "estimate",
		)
		.map((item): EstimateDocumentSummary => {
			if (
				typeof item.id !== "string" ||
				!SAFE_DOCUMENT_ID.test(item.id) ||
				typeof item.projectId !== "string" ||
				!SAFE_PROJECT_ID.test(item.projectId) ||
				item.category !== "estimates" ||
				item.kind !== "estimate" ||
				typeof item.version !== "number" ||
				!Number.isInteger(item.version) ||
				item.version < 1 ||
				typeof item.rowCount !== "number" ||
				!Number.isInteger(item.rowCount) ||
				item.rowCount < 0 ||
				typeof item.total !== "string" ||
				!TOTAL_TEXT.test(item.total) ||
				item.currency !== "RUB" ||
				typeof item.editable !== "boolean" ||
				typeof item.status !== "string" ||
				!isTimestamp(item.updatedAt)
			) {
				throw new Error("Document catalog contains an invalid estimate.");
			}
			return {
				id: item.id,
				projectId: item.projectId,
				projectName: readBoundedText(item.projectName, "projectName", 240),
				name: readBoundedText(item.name, "name", 240),
				status: item.status,
				version: item.version,
				updatedAt: item.updatedAt,
				rowCount: item.rowCount,
				total: item.total,
				currency: "RUB",
				editable: item.editable,
			};
		});
};

export const parseEstimate = (value: unknown): NativeEstimate => {
	if (
		!isRecord(value) ||
		value.schemaId !== "kolibri.estimate_draft" ||
		!["1.2", "1.3", "1.4"].includes(String(value.schemaVersion)) ||
		typeof value.projectId !== "string" ||
		!SAFE_PROJECT_ID.test(value.projectId) ||
		typeof value.documentId !== "string" ||
		!SAFE_DOCUMENT_ID.test(value.documentId) ||
		typeof value.version !== "number" ||
		!Number.isInteger(value.version) ||
		value.version < 1 ||
		typeof value.status !== "string" ||
		value.currency !== "RUB" ||
		!Array.isArray(value.rows) ||
		!isRecord(value.totals) ||
		typeof value.totals.subtotal !== "string" ||
		!TOTAL_TEXT.test(value.totals.subtotal) ||
		typeof value.totals.total !== "string" ||
		!TOTAL_TEXT.test(value.totals.total)
	) {
		throw new Error("Estimate response is invalid.");
	}
	const schemaVersion = value.schemaVersion as NativeEstimate["schemaVersion"];
	let generation: NativeEstimateGeneration | null | undefined;
	if (value.generation === null) {
		generation = null;
	} else if (value.generation !== undefined) {
		if (
			!isRecord(value.generation) ||
			typeof value.generation.providerProfile !== "string" ||
			!PROVIDER_PROFILE.test(value.generation.providerProfile) ||
			typeof value.generation.runId !== "string" ||
			!CHAT_RUN_ID.test(value.generation.runId) ||
			(value.generation.technologyCardHash !== undefined &&
				(typeof value.generation.technologyCardHash !== "string" ||
					!SHA256.test(value.generation.technologyCardHash))) ||
			(value.generation.qualityStatus !== undefined &&
				!["pending", "failed", "passed"].includes(
					String(value.generation.qualityStatus),
				))
		) {
			throw new Error("Estimate generation provenance is invalid.");
		}
		generation = {
			providerProfile: value.generation.providerProfile,
			runId: value.generation.runId,
			estimateGenerationRunId: readOptionalText(
				value.generation.estimateGenerationRunId,
				"estimateGenerationRunId",
			),
			technologyCardRevisionId: readOptionalText(
				value.generation.technologyCardRevisionId,
				"technologyCardRevisionId",
			),
			technologyCardHash: value.generation.technologyCardHash as
				| string
				| undefined,
			qualityStatus: value.generation.qualityStatus as
				| NativeEstimateGeneration["qualityStatus"]
				| undefined,
		};
	}
	let rowPage: NativeEstimateRowPage | undefined;
	if (value.rowPage !== undefined) {
		if (
			!isRecord(value.rowPage) ||
			typeof value.rowPage.offset !== "number" ||
			!Number.isInteger(value.rowPage.offset) ||
			value.rowPage.offset < 0 ||
			typeof value.rowPage.limit !== "number" ||
			!Number.isInteger(value.rowPage.limit) ||
			value.rowPage.limit < 0 ||
			value.rowPage.limit > NATIVE_ESTIMATE_PAGE_SIZE ||
			typeof value.rowPage.totalRows !== "number" ||
			!Number.isInteger(value.rowPage.totalRows) ||
			value.rowPage.totalRows < 0 ||
			value.rowPage.totalRows > 1_000_000 ||
			typeof value.rowPage.hasMore !== "boolean"
		) {
			throw new Error("Estimate row page is invalid.");
		}
		rowPage = {
			offset: value.rowPage.offset,
			limit: value.rowPage.limit,
			totalRows: value.rowPage.totalRows,
			hasMore: value.rowPage.hasMore,
		};
	}
	if (
		(schemaVersion === "1.4" && rowPage === undefined) ||
		(rowPage !== undefined &&
			(value.rows.length > rowPage.limit ||
				rowPage.offset + value.rows.length > rowPage.totalRows ||
				rowPage.hasMore !==
					(rowPage.offset + value.rows.length < rowPage.totalRows)))
	) {
		throw new Error("Estimate row page is inconsistent.");
	}

	const rows = value.rows.map((row): NativeEstimateRow => {
		if (
			!isRecord(row) ||
			typeof row.id !== "string" ||
			!SAFE_ROW_ID.test(row.id) ||
			!ROW_KINDS.includes(row.kind as NativeEstimateRow["kind"]) ||
			typeof row.quantity !== "string" ||
			!DECIMAL_TEXT.test(row.quantity) ||
			typeof row.unitPrice !== "string" ||
			!MONEY_TEXT.test(row.unitPrice) ||
			typeof row.lineTotal !== "string" ||
			!TOTAL_TEXT.test(row.lineTotal) ||
			(row.lineConfidence !== undefined &&
				!LINE_CONFIDENCE.includes(
					row.lineConfidence as NativeEstimateRow["lineConfidence"],
				))
		) {
			throw new Error("Estimate contains an invalid row.");
		}
		return {
			id: row.id,
			section: readBoundedText(row.section, "section", 120),
			kind: row.kind as NativeEstimateRow["kind"],
			description: readBoundedText(row.description, "description", 300),
			unit: readBoundedText(row.unit, "unit", 32),
			quantity: row.quantity,
			unitPrice: row.unitPrice,
			lineTotal: row.lineTotal,
			quantityBasis: readBoundedText(row.quantityBasis, "quantityBasis", 500),
			priceBasis: readBoundedText(row.priceBasis, "priceBasis", 500),
			operationId: readOptionalText(row.operationId, "operationId"),
			technologyCardVersion: readOptionalText(
				row.technologyCardVersion,
				"technologyCardVersion",
			),
			resourceId: readOptionalText(row.resourceId, "resourceId"),
			evidenceId: readOptionalText(row.evidenceId, "evidenceId"),
			wbsPath: readOptionalText(row.wbsPath, "wbsPath", 500),
			specification: readOptionalText(
				row.specification,
				"specification",
				500,
			),
			quantityFormula: readOptionalText(
				row.quantityFormula,
				"quantityFormula",
				500,
			),
			catalogEntryId: readOptionalText(row.catalogEntryId, "catalogEntryId"),
			catalogEntryVersion:
				typeof row.catalogEntryVersion === "number" &&
				Number.isInteger(row.catalogEntryVersion) &&
				row.catalogEntryVersion > 0
					? row.catalogEntryVersion
					: undefined,
			priceObservationId: readOptionalText(
				row.priceObservationId,
				"priceObservationId",
			),
			marketAggregateId: readOptionalText(
				row.marketAggregateId,
				"marketAggregateId",
			),
			lineConfidence:
				(row.lineConfidence as NativeEstimateRow["lineConfidence"] | undefined) ??
				"missing",
		};
	});

	return {
		schemaId: "kolibri.estimate_draft",
		schemaVersion,
		projectId: value.projectId,
		documentId: value.documentId,
		version: value.version,
		status: value.status,
		estimateTitle: readBoundedText(value.estimateTitle, "estimateTitle", 240),
		currency: "RUB",
		rows,
		...(rowPage ? { rowPage } : {}),
		...(generation !== undefined ? { generation } : {}),
		totals: {
			subtotal: value.totals.subtotal,
			total: value.totals.total,
		},
	};
};

export const isNativeEstimateDraftValid = (
	title: string,
	rows: readonly NativeEstimateRow[],
) =>
	title.trim().length > 0 &&
	title.length <= 240 &&
	rows.every(
		(row) =>
			row.description.trim().length > 0 &&
			row.description.length <= 300 &&
			row.unit.trim().length > 0 &&
			row.unit.length <= 32 &&
			DECIMAL_TEXT.test(row.quantity) &&
			MONEY_TEXT.test(row.unitPrice),
	);

export const estimatePatchBody = (
	estimate: NativeEstimate,
	title: string,
	rows: readonly NativeEstimateRow[],
) => {
	const toUpsert = ({ lineTotal: _lineTotal, ...row }: NativeEstimateRow) => {
		void _lineTotal;
		return {
			...row,
			description: row.description.trim(),
			unit: row.unit.trim(),
		};
	};
	const baseline = new Map(
		estimate.rows.map((row) => [row.id, JSON.stringify(toUpsert(row))]),
	);
	const currentIds = new Set(rows.map((row) => row.id));
	const upsertRows = rows
		.map(toUpsert)
		.filter((row) => baseline.get(row.id) !== JSON.stringify(row));
	const deleteRowIds = estimate.rows
		.filter((row) => !currentIds.has(row.id))
		.map((row) => row.id);
	const normalizedTitle = title.trim();
	return {
		version: estimate.version,
		...(normalizedTitle !== estimate.estimateTitle
			? { title: normalizedTitle }
			: {}),
		upsertRows,
		deleteRowIds,
		returnPage: {
			offset: estimate.rowPage?.offset ?? 0,
			limit: NATIVE_ESTIMATE_PAGE_SIZE,
		},
	};
};

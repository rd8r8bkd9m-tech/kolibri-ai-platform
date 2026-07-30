const SAFE_PROJECT_ID = /^project_[A-Za-z0-9._~-]{8,96}$/;
const SAFE_DOCUMENT_ID = /^document_[A-Za-z0-9._~-]{8,96}$/;
const SAFE_ROW_ID = /^row_[A-Za-z0-9._~-]{8,96}$/;
const DECIMAL_TEXT = /^(?:0|[1-9]\d{0,11})(?:\.\d{1,6})?$/;
const MONEY_TEXT = /^(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$/;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isTimestamp = (value: unknown): value is string =>
  typeof value === "string" &&
  value.length <= 64 &&
  Number.isFinite(Date.parse(value));

const readBoundedText = (
  value: unknown,
  field: string,
  maximum: number,
) => {
  if (
    typeof value !== "string" ||
    value.trim().length === 0 ||
    value.length > maximum
  ) {
    throw new Error(`Estimate field ${field} is invalid.`);
  }
  return value;
};

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
  kind: "work" | "material" | "equipment" | "service";
  description: string;
  unit: string;
  quantity: string;
  unitPrice: string;
  lineTotal: string;
  quantityBasis: string;
  priceBasis: string;
};

export type NativeEstimate = {
  schemaId: "kolibri.estimate_draft";
  schemaVersion: "1.2";
  projectId: string;
  documentId: string;
  version: number;
  status: string;
  estimateTitle: string;
  currency: "RUB";
  rows: readonly NativeEstimateRow[];
};

export const parseEstimateCatalog = (
  value: unknown,
): readonly EstimateDocumentSummary[] => {
  if (!isRecord(value) || !Array.isArray(value.documents)) {
    throw new Error("Document catalog is invalid.");
  }
  return value.documents.map((item): EstimateDocumentSummary => {
    if (
      !isRecord(item) ||
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
      !MONEY_TEXT.test(item.total) ||
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
    value.schemaVersion !== "1.2" ||
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
    value.rows.length > 200
  ) {
    throw new Error("Estimate response is invalid.");
  }

  const rows = value.rows.map((row): NativeEstimateRow => {
    if (
      !isRecord(row) ||
      typeof row.id !== "string" ||
      !SAFE_ROW_ID.test(row.id) ||
      !["work", "material", "equipment", "service"].includes(
        String(row.kind),
      ) ||
      typeof row.quantity !== "string" ||
      !DECIMAL_TEXT.test(row.quantity) ||
      typeof row.unitPrice !== "string" ||
      !MONEY_TEXT.test(row.unitPrice) ||
      typeof row.lineTotal !== "string" ||
      !MONEY_TEXT.test(row.lineTotal)
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
      quantityBasis: readBoundedText(
        row.quantityBasis,
        "quantityBasis",
        500,
      ),
      priceBasis: readBoundedText(row.priceBasis, "priceBasis", 500),
    };
  });

  return {
    schemaId: "kolibri.estimate_draft",
    schemaVersion: "1.2",
    projectId: value.projectId,
    documentId: value.documentId,
    version: value.version,
    status: value.status,
    estimateTitle: readBoundedText(
      value.estimateTitle,
      "estimateTitle",
      240,
    ),
    currency: "RUB",
    rows,
  };
};

export const isNativeEstimateDraftValid = (
  title: string,
  rows: readonly NativeEstimateRow[],
) =>
  title.trim().length > 0 &&
  title.length <= 240 &&
  rows.length <= 200 &&
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
) => ({
  version: estimate.version,
  title: title.trim(),
  currency: "RUB" as const,
  rows: rows.map(
    ({
      lineTotal: _lineTotal,
      ...row
    }) => ({
      ...row,
      description: row.description.trim(),
      unit: row.unit.trim(),
    }),
  ),
});

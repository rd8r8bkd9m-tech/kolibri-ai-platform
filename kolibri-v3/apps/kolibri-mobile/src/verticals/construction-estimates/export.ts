export type EstimateExportFormat = "pdf" | "xlsx" | "docx" | "csv";

export type EstimateExportResult = {
	blob: Blob;
	filename: string;
	mimeType: string;
	format: EstimateExportFormat;
	version: number;
	shareUrl?: string;
};

const FORMATS: readonly EstimateExportFormat[] = [
	"pdf",
	"xlsx",
	"docx",
	"csv",
];

export const ESTIMATE_EXPORT_FORMATS = FORMATS;

export const estimateExportMediaType = (
	format: EstimateExportFormat,
): string => {
	switch (format) {
		case "pdf":
			return "application/pdf";
		case "xlsx":
			return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
		case "docx":
			return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
		case "csv":
			return "text/csv; charset=utf-8";
	}
};

export const isEstimateExportFormat = (
	value: unknown,
): value is EstimateExportFormat =>
	typeof value === "string" &&
	FORMATS.includes(value as EstimateExportFormat);

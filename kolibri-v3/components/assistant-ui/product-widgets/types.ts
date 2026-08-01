import type { z } from "zod";

import { kolibriGenerativeUIComponentSchemas } from "@/lib/generative-ui/schema";

export type WeatherWidgetProps = z.infer<
	typeof kolibriGenerativeUIComponentSchemas.WeatherWidget
>;

export type EstimateWidgetProps = z.infer<
	typeof kolibriGenerativeUIComponentSchemas.EstimateEditor
>;

export type EstimateRow = EstimateWidgetProps["rows"][number];
export type EditableEstimateRow = Omit<EstimateRow, "lineTotal">;
export type PriceEvidence = NonNullable<EstimateRow["priceEvidence"]>;
export type EnginePriceProvenance = NonNullable<
	EstimateRow["enginePriceProvenance"]
>;

export type ProjectPartySummary = {
	id: string;
	role: "client" | "contractor";
	entityType: "person" | "organization";
	displayName: string;
	taxId: string | null;
	registrationCode: string | null;
};

export type ProjectContextSummary = {
	projectName: string;
	objectName: string | null;
	client: ProjectPartySummary | null;
	contractor: ProjectPartySummary | null;
};

export type EstimateCopyResult = {
	project: {
		id: string;
		name: string;
		objectName: string;
		threadId: string;
	};
	document: { id: string; version: number; contentHash: string };
	lineage: {
		sourceProjectId: string;
		sourceDocumentId: string;
		sourceVersion: number;
		sourceContentHash: string;
	};
};

export type EstimateExportFormat = "pdf" | "xlsx" | "docx" | "csv" | "zip";

export type MessageContentPart = {
	type: string;
	[key: string]: unknown;
};

export const isRecord = (value: unknown): value is Record<string, unknown> =>
	typeof value === "object" && value !== null && !Array.isArray(value);

export const containsEstimateDocument = (
	content: readonly MessageContentPart[],
	documentId: string,
) =>
	content.some(
		(part) =>
			part.type === "tool-call" &&
			isRecord(part.args) &&
			part.args["$type"] === "EstimateEditor" &&
			part.args.documentId === documentId,
	);

export type WeatherScene =
	| "clear-day"
	| "clear-night"
	| "clouds"
	| "rain"
	| "snow"
	| "storm";

export type EstimateEditorWidgetProps = EstimateWidgetProps & {
	presentation?: "canvas" | "inline";
};

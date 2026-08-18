import {
	parseEstimate,
	type NativeEstimate,
} from "@/src/verticals/construction-estimates/contracts";

export type EstimateEditorWidget = {
	kind: "estimate-editor";
	estimate: NativeEstimate;
	projectId: string;
	documentId: string;
	version: number;
};

export type EstimateGenerationActivityWidget = {
	kind: "estimate-generation-activity";
	projectId: string;
	generationRunId: string;
	projectCaseVersion: number;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
	typeof value === "object" && value !== null && !Array.isArray(value);

export const parseEstimateEditorWidget = (
	value: unknown,
): EstimateEditorWidget | null => {
	if (!isRecord(value) || value.$type !== "EstimateEditor") return null;
	try {
		const estimate = parseEstimate(value);
		return {
			kind: "estimate-editor",
			estimate,
			projectId: estimate.projectId,
			documentId: estimate.documentId,
			version: estimate.version,
		};
	} catch {
		return null;
	}
};

export const parseEstimateGenerationActivity = (
	value: unknown,
): EstimateGenerationActivityWidget | null => {
	if (!isRecord(value) || value.$type !== "EstimateGenerationActivity") {
		return null;
	}
	if (
		typeof value.activityProjectId !== "string" ||
		typeof value.generationRunId !== "string" ||
		typeof value.projectCaseVersion !== "number"
	) {
		return null;
	}
	return {
		kind: "estimate-generation-activity",
		projectId: value.activityProjectId,
		generationRunId: value.generationRunId,
		projectCaseVersion: value.projectCaseVersion,
	};
};

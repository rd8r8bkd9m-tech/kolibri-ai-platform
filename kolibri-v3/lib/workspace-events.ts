export const KOLIBRI_OPEN_ESTIMATE_EVENT = "kolibri:open-estimate";
export const KOLIBRI_DOCUMENTS_CHANGED_EVENT = "kolibri:documents-changed";
export const KOLIBRI_OPEN_MODEL_SETTINGS_EVENT = "kolibri:open-model-settings";
export const KOLIBRI_ACTIVATE_AGENT_TASK_EVENT = "kolibri:activate-agent-task";

const SAFE_WORKSPACE_ID = /^[A-Za-z0-9][A-Za-z0-9._:~-]{7,191}$/;

export type OpenEstimateDetail = {
	documentId: string;
	projectId: string;
	projectName?: string;
	title: string;
	version: number;
};

export type ActivateAgentTaskDetail = {
	projectId: string;
	runId: string;
	threadId: string;
};

export function openEstimateInWorkspace(detail: OpenEstimateDetail) {
	window.dispatchEvent(
		new CustomEvent<OpenEstimateDetail>(KOLIBRI_OPEN_ESTIMATE_EVENT, {
			detail,
		}),
	);
}

export function announceDocumentsChanged() {
	window.dispatchEvent(new Event(KOLIBRI_DOCUMENTS_CHANGED_EVENT));
}

export function openModelSettings() {
	window.dispatchEvent(new Event(KOLIBRI_OPEN_MODEL_SETTINGS_EVENT));
}

export function activateAgentTaskInWorkspace(detail: ActivateAgentTaskDetail) {
	window.dispatchEvent(
		new CustomEvent<ActivateAgentTaskDetail>(
			KOLIBRI_ACTIVATE_AGENT_TASK_EVENT,
			{ detail },
		),
	);
}

export function isActivateAgentTaskDetail(
	value: unknown,
): value is ActivateAgentTaskDetail {
	if (typeof value !== "object" || value === null) return false;
	const candidate = value as Partial<ActivateAgentTaskDetail>;
	return (
		typeof candidate.projectId === "string" &&
		SAFE_WORKSPACE_ID.test(candidate.projectId) &&
		typeof candidate.runId === "string" &&
		SAFE_WORKSPACE_ID.test(candidate.runId) &&
		typeof candidate.threadId === "string" &&
		SAFE_WORKSPACE_ID.test(candidate.threadId)
	);
}

export function isOpenEstimateDetail(
	value: unknown,
): value is OpenEstimateDetail {
	if (typeof value !== "object" || value === null) return false;
	const candidate = value as Partial<OpenEstimateDetail>;
	return (
		typeof candidate.documentId === "string" &&
		candidate.documentId.startsWith("document_") &&
		typeof candidate.projectId === "string" &&
		candidate.projectId.startsWith("project_") &&
		typeof candidate.title === "string" &&
		candidate.title.trim().length > 0 &&
		typeof candidate.version === "number" &&
		Number.isInteger(candidate.version) &&
		candidate.version >= 1
	);
}

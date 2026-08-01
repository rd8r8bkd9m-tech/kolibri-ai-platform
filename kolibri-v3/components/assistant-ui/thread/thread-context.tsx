"use client";

import {
	type AssistantState,
	MessagePrimitive,
	groupPartByType,
	type ToolCallMessagePartComponent,
} from "@assistant-ui/react";
import { createContext, type ComponentType, type PropsWithChildren } from "react";

export type ThreadGroupPart = MessagePrimitive.GroupedParts.GroupPart;

export type ThreadComponents = {
	AssistantMessage?: ComponentType | undefined;
	Welcome?: ComponentType | undefined;
	ToolFallback?: ToolCallMessagePartComponent | undefined;
	ToolGroup?:
		| ComponentType<PropsWithChildren<{ group: ThreadGroupPart }>>
		| undefined;
	ReasoningGroup?:
		| ComponentType<PropsWithChildren<{ group: ThreadGroupPart }>>
		| undefined;
};

export type ThreadProps = {
	compact?: boolean | undefined;
	components?: ThreadComponents | undefined;
	onOpenAccount?: (() => void) | undefined;
	onOpenContextPanel?: (() => void) | undefined;
	workspaceOpen?: boolean | undefined;
};

export const EMPTY_COMPONENTS: ThreadComponents = {};

export const ThreadComponentsContext =
	createContext<ThreadComponents>(EMPTY_COMPONENTS);
export const ThreadCompactContext = createContext<boolean>(false);
export const ThreadNavigationContext = createContext<{
	onOpenAccount?: (() => void) | undefined;
	onOpenContextPanel?: (() => void) | undefined;
	workspaceOpen?: boolean | undefined;
}>({});

const defaultAssistantPartGroup = groupPartByType({
	reasoning: ["group-chainOfThought", "group-reasoning"],
	"tool-call": ["group-chainOfThought", "group-tool"],
	"standalone-tool-call": [],
});

const PRODUCT_STAGE_TOOLS = new Set([
	"project_case_analysis",
	"technology_card_build",
	"price_candidates_apply",
	"price_candidates_verify",
	"estimate_engine_calculate",
	"estimate_verification",
]);

export const groupAssistantPart: typeof defaultAssistantPartGroup = (part, context) => {
	if (
		part.type === "tool-call" &&
		(part.toolName === "present" ||
			part.toolName === "get_weather" ||
			PRODUCT_STAGE_TOOLS.has(part.toolName))
	) {
		return [];
	}
	return defaultAssistantPartGroup(part, context);
};

export const weatherPartFingerprint = (part: { args: unknown; result?: unknown }) => {
	try {
		return JSON.stringify({
			args: part.args,
			result: part.result,
		});
	} catch {
		return null;
	}
};

export const isNewChatView = (s: AssistantState) => {
	const activeThreadId = s.threads.mainThreadId;
	const activeThread =
		activeThreadId === null
			? null
			: s.threads.threadItems.find((thread) => thread.id === activeThreadId);
	const isDraft = activeThread?.custom?.draft === true;

	return isDraft
		? s.thread.messages.length === 0 &&
				(!s.thread.isLoading || s.threads.isLoading)
		: false;
};

export const isRecord = (value: unknown): value is Record<string, unknown> =>
	typeof value === "object" && value !== null && !Array.isArray(value);

export type ShareableEstimate = {
	documentId: string | null;
	projectId: string;
	version: number;
	title: string;
	region: string | null;
	total: string | null;
};

export const readShareableEstimate = (
	content: readonly {
		type: string;
		[key: string]: unknown;
	}[],
): ShareableEstimate | null => {
	for (const part of content) {
		if (
			part.type !== "tool-call" ||
			part.toolName !== "present" ||
			!isRecord(part.args) ||
			part.args.$type !== "EstimateEditor" ||
			typeof part.args.projectId !== "string" ||
			typeof part.args.version !== "number"
		) {
			continue;
		}

		const totals = isRecord(part.args.totals) ? part.args.totals : null;
		const rawTotal = totals?.total;
		return {
			documentId:
				typeof part.args.documentId === "string" ? part.args.documentId : null,
			projectId: part.args.projectId,
			version: part.args.version,
			title:
				typeof part.args.estimateTitle === "string"
					? part.args.estimateTitle
					: "Смета Kolibri",
			region:
				typeof part.args.estimateRegion === "string"
					? part.args.estimateRegion
					: null,
			total:
				typeof rawTotal === "string" || typeof rawTotal === "number"
					? String(rawTotal)
					: null,
		};
	}
	return null;
};

"use client";

import {
	boundedText,
	integer,
	isRecord,
	platformAdminRequest,
	type PlatformAdminPage,
} from "@/lib/platform-admin/client";

const AGENT_ID = /^[a-z0-9][a-z0-9._-]{2,127}$/;
const MODEL_PROFILE = /^[a-z0-9][a-z0-9._-]{1,95}$/;

export type ConstructionAgentCard = {
	agentId: string;
	moduleId: "construction";
	displayName: string;
	role: string;
	systemPrompt: string;
	skills: string[];
	capabilities: string[];
	allowedTools: string[];
	authorityLimits: Record<string, unknown>;
	forbiddenActions: string[];
	requiredEvidence: string[];
	handoffRules: string[];
	completionCriteria: string[];
	modelProfile: string;
	cardVersion: string;
	configurationRevision: number;
	source: "built_in" | "configured";
	updatedAt: number | null;
};

const stringList = (value: unknown, maximum = 256) => {
	if (
		!Array.isArray(value) ||
		value.length > maximum ||
		value.some((item) => typeof item !== "string" || item.length > 500)
	) {
		return null;
	}
	return value as string[];
};

function parseConstructionAgent(value: unknown): ConstructionAgentCard | null {
	if (!isRecord(value) || !isRecord(value.authorityLimits)) return null;
	const agentId = boundedText(value.agentId, 128);
	const displayName = boundedText(value.displayName, 160);
	const role = boundedText(value.role, 120);
	const systemPrompt = boundedText(value.systemPrompt, 32768);
	const modelProfile = boundedText(value.modelProfile, 96);
	const cardVersion = boundedText(value.cardVersion, 64);
	const skills = stringList(value.skills);
	const capabilities = stringList(value.capabilities);
	const allowedTools = stringList(value.allowedTools);
	const forbiddenActions = stringList(value.forbiddenActions);
	const requiredEvidence = stringList(value.requiredEvidence);
	const handoffRules = stringList(value.handoffRules);
	const completionCriteria = stringList(value.completionCriteria);
	const configurationRevision = integer(
		value.configurationRevision,
		0,
		Number.MAX_SAFE_INTEGER,
	);
	const updatedAt =
		value.updatedAt === null
			? null
			: integer(value.updatedAt, 0, Number.MAX_SAFE_INTEGER);
	if (
		!agentId ||
		!AGENT_ID.test(agentId) ||
		value.moduleId !== "construction" ||
		!displayName ||
		!role ||
		!systemPrompt ||
		!modelProfile ||
		!MODEL_PROFILE.test(modelProfile) ||
		!cardVersion ||
		!skills ||
		!capabilities ||
		!allowedTools ||
		!forbiddenActions ||
		!requiredEvidence ||
		!handoffRules ||
		!completionCriteria ||
		configurationRevision === null ||
		(value.source !== "built_in" && value.source !== "configured") ||
		(value.updatedAt !== null && updatedAt === null)
	) {
		return null;
	}
	return {
		agentId,
		moduleId: "construction",
		displayName,
		role,
		systemPrompt,
		skills,
		capabilities,
		allowedTools,
		authorityLimits: value.authorityLimits,
		forbiddenActions,
		requiredEvidence,
		handoffRules,
		completionCriteria,
		modelProfile,
		cardVersion,
		configurationRevision,
		source: value.source,
		updatedAt,
	};
}

function parsePage(value: unknown): PlatformAdminPage<ConstructionAgentCard> {
	if (!isRecord(value) || !Array.isArray(value.items)) {
		throw new Error("Реестр агентов вернул некорректный список.");
	}
	const items = value.items.map(parseConstructionAgent);
	const nextCursor =
		value.nextCursor === null ? null : boundedText(value.nextCursor, 128);
	if (
		items.some((item) => item === null) ||
		(value.nextCursor !== null && (!nextCursor || !AGENT_ID.test(nextCursor)))
	) {
		throw new Error("Реестр агентов вернул некорректные данные.");
	}
	return {
		items: items as ConstructionAgentCard[],
		nextCursor,
	};
}

export async function getConstructionAgentsPage(
	options: {
		cursor?: string;
		query?: string;
		signal?: AbortSignal;
	} = {},
) {
	if (options.cursor && !AGENT_ID.test(options.cursor)) {
		throw new Error("Некорректный cursor агентов.");
	}
	const parameters = new URLSearchParams({ limit: "50" });
	if (options.cursor) parameters.set("cursor", options.cursor);
	const query = options.query?.trim();
	if (query) parameters.set("q", query.slice(0, 160));
	return parsePage(
		await platformAdminRequest(
			`/api/superadmin/modules/construction/agents?${parameters.toString()}`,
			{ signal: options.signal },
		),
	);
}

export async function updateConstructionAgent(
	agentId: string,
	update: {
		revision: number;
		systemPrompt: string;
		modelProfile: string;
	},
) {
	if (!AGENT_ID.test(agentId)) throw new Error("Некорректный Agent ID.");
	const agent = parseConstructionAgent(
		await platformAdminRequest(
			`/api/superadmin/modules/construction/agents/${agentId}`,
			{ method: "PATCH", body: JSON.stringify(update) },
		),
	);
	if (!agent) throw new Error("Backend вернул некорректную Agent Card.");
	return agent;
}

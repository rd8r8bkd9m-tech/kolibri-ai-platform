"use client";

import { withCsrfHeader } from "@/lib/csrf";

const SAFE_MODEL_ID = /^[A-Za-z0-9][A-Za-z0-9._~-]{0,159}$/;

export type PlatformModel = {
	id: string;
	providerType: string;
	providerName: string;
	baseUrl: string | null;
	modelId: string;
	displayName: string;
	description: string;
	autoPriority: number;
	isEnabled: boolean;
	isDefault: boolean;
	supportedReasoningEfforts: Array<{ id: string; description: string }>;
	serviceTiers: Array<{ id: string; name: string; description: string }>;
	lastTestedAt: string | null;
	lastTestStatus: string | null;
	createdAt: string;
	updatedAt: string;
};

export type PlatformModelCreate = {
	providerType: string;
	providerName?: string;
	apiKey: string;
	baseUrl?: string;
	modelId: string;
	displayName: string;
	description?: string;
	autoPriority?: number;
	isDefault?: boolean;
	supportedReasoningEfforts?: Array<{ id: string; description: string }>;
	serviceTiers?: Array<{ id: string; name: string; description: string }>;
};

export type PlatformModelUpdate = {
	displayName?: string;
	description?: string;
	autoPriority?: number;
	isEnabled?: boolean;
	isDefault?: boolean;
	apiKey?: string;
};

export type PlatformModelTestResult = {
	status: "connected" | "failed";
	message: string;
	error?: string;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
	typeof value === "object" && value !== null && !Array.isArray(value);

function parseModel(value: unknown): PlatformModel | null {
	if (!isRecord(value)) return null;
	if (typeof value.id !== "string") return null;
	if (typeof value.providerType !== "string") return null;
	if (typeof value.modelId !== "string") return null;
	if (typeof value.displayName !== "string") return null;
	return {
		id: value.id,
		providerType: value.providerType,
		providerName:
			typeof value.providerName === "string" ? value.providerName : "",
		baseUrl: typeof value.baseUrl === "string" ? value.baseUrl : null,
		modelId: value.modelId,
		displayName: value.displayName,
		description: typeof value.description === "string" ? value.description : "",
		autoPriority:
			typeof value.autoPriority === "number" ? value.autoPriority : 50,
		isEnabled: value.isEnabled === true,
		isDefault: value.isDefault === true,
		supportedReasoningEfforts: Array.isArray(
			value.supportedReasoningEfforts,
		)
			? value.supportedReasoningEfforts
			: [],
		serviceTiers: Array.isArray(value.serviceTiers) ? value.serviceTiers : [],
		lastTestedAt:
			typeof value.lastTestedAt === "string" ? value.lastTestedAt : null,
		lastTestStatus:
			typeof value.lastTestStatus === "string"
				? value.lastTestStatus
				: null,
		createdAt: typeof value.createdAt === "string" ? value.createdAt : "",
		updatedAt: typeof value.updatedAt === "string" ? value.updatedAt : "",
	};
}

async function modelRequest(path: string, init: RequestInit = {}) {
	const response = await fetch(path, {
		...init,
		headers:
			init.method && init.method !== "GET"
				? withCsrfHeader({
						Accept: "application/json",
						"Content-Type": "application/json",
						...init.headers,
					})
				: { Accept: "application/json", ...init.headers },
		credentials: "same-origin",
		cache: "no-store",
	});
	const text = await response.text();
	let payload: unknown;
	try {
		payload = JSON.parse(text);
	} catch {
		throw new Error("Сервер вернул некорректный ответ.");
	}
	if (!response.ok) {
		const message =
			isRecord(payload) && typeof payload.message === "string"
				? payload.message
				: "Действие не выполнено.";
		throw new Error(message);
	}
	return payload;
}

export async function getPlatformModels(
	signal?: AbortSignal,
): Promise<PlatformModel[]> {
	const payload = await modelRequest("/api/superadmin/models", { signal });
	if (!isRecord(payload) || !Array.isArray(payload.models)) {
		throw new Error("Сервер вернул некорректный список моделей.");
	}
	const models = payload.models.map(parseModel);
	if (models.some((m) => m === null)) {
		throw new Error("Сервер вернул некорректные данные моделей.");
	}
	return models as PlatformModel[];
}

export async function createPlatformModel(
	data: PlatformModelCreate,
): Promise<PlatformModel> {
	const payload = await modelRequest("/api/superadmin/models", {
		method: "POST",
		body: JSON.stringify(data),
	});
	if (!isRecord(payload) || !isRecord(payload.model)) {
		throw new Error("Сервер вернул некорректный ответ.");
	}
	const model = parseModel(payload.model);
	if (!model) throw new Error("Сервер вернул некорректные данные модели.");
	return model;
}

export async function updatePlatformModel(
	modelId: string,
	data: PlatformModelUpdate,
): Promise<PlatformModel> {
	if (!SAFE_MODEL_ID.test(modelId)) {
		throw new Error("Некорректный ID модели.");
	}
	const payload = await modelRequest(
		`/api/superadmin/models/${encodeURIComponent(modelId)}`,
		{ method: "PATCH", body: JSON.stringify(data) },
	);
	if (!isRecord(payload) || !isRecord(payload.model)) {
		throw new Error("Сервер вернул некорректный ответ.");
	}
	const model = parseModel(payload.model);
	if (!model) throw new Error("Сервер вернул некорректные данные модели.");
	return model;
}

export async function deletePlatformModel(modelId: string): Promise<void> {
	if (!SAFE_MODEL_ID.test(modelId)) {
		throw new Error("Некорректный ID модели.");
	}
	await modelRequest(
		`/api/superadmin/models/${encodeURIComponent(modelId)}`,
		{ method: "DELETE" },
	);
}

export async function testPlatformModel(
	modelId: string,
): Promise<PlatformModelTestResult> {
	if (!SAFE_MODEL_ID.test(modelId)) {
		throw new Error("Некорректный ID модели.");
	}
	const payload = await modelRequest(
		`/api/superadmin/models/${encodeURIComponent(modelId)}/test`,
		{ method: "POST" },
	);
	if (!isRecord(payload) || typeof payload.status !== "string") {
		throw new Error("Сервер вернул некорректный ответ.");
	}
	return {
		status: payload.status as "connected" | "failed",
		message:
			typeof payload.message === "string"
				? payload.message
				: "Неизвестный результат.",
		error: typeof payload.error === "string" ? payload.error : undefined,
	};
}

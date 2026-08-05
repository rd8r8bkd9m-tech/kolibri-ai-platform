"use client";

import { withCsrfHeader } from "@/lib/csrf";

const SAFE_MODEL_ID = /^[A-Za-z0-9][A-Za-z0-9._~-]{0,159}$/;

export type UserManagedModel = {
	id: string;
	providerType: string;
	providerName: string;
	baseUrl: string | null;
	modelId: string;
	displayName: string;
	autoPriority: number;
	isEnabled: boolean;
	lastTestedAt: string | null;
	lastTestStatus: string | null;
	createdAt: string;
	updatedAt: string;
};

export type UserModelCreate = {
	providerType: string;
	providerName?: string;
	apiKey: string;
	baseUrl?: string;
	modelId: string;
	displayName: string;
	autoPriority?: number;
};

export type UserModelUpdate = {
	displayName?: string;
	autoPriority?: number;
	isEnabled?: boolean;
	apiKey?: string;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
	typeof value === "object" && value !== null && !Array.isArray(value);

function parseModel(value: unknown): UserManagedModel | null {
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
		autoPriority:
			typeof value.autoPriority === "number" ? value.autoPriority : 50,
		isEnabled: value.isEnabled === true,
		lastTestedAt:
			typeof value.lastTestedAt === "string" ? value.lastTestedAt : null,
		lastTestStatus:
			typeof value.lastTestStatus === "string" ? value.lastTestStatus : null,
		createdAt: typeof value.createdAt === "string" ? value.createdAt : "",
		updatedAt: typeof value.updatedAt === "string" ? value.updatedAt : "",
	};
}

async function userModelRequest(path: string, init: RequestInit = {}) {
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

export async function getUserModels(
	signal?: AbortSignal,
): Promise<UserManagedModel[]> {
	const payload = await userModelRequest("/api/v3/user-models", { signal });
	if (!isRecord(payload) || !Array.isArray(payload.models)) {
		throw new Error("Сервер вернул некорректный список моделей.");
	}
	const models = payload.models.map(parseModel);
	if (models.some((m) => m === null)) {
		throw new Error("Сервер вернул некорректные данные моделей.");
	}
	return models as UserManagedModel[];
}

export async function createUserModel(
	data: UserModelCreate,
): Promise<UserManagedModel> {
	const payload = await userModelRequest("/api/v3/user-models", {
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

export async function updateUserModel(
	modelId: string,
	data: UserModelUpdate,
): Promise<UserManagedModel> {
	if (!SAFE_MODEL_ID.test(modelId)) {
		throw new Error("Некорректный ID модели.");
	}
	const payload = await userModelRequest(
		`/api/v3/user-models/${encodeURIComponent(modelId)}`,
		{ method: "PATCH", body: JSON.stringify(data) },
	);
	if (!isRecord(payload) || !isRecord(payload.model)) {
		throw new Error("Сервер вернул некорректный ответ.");
	}
	const model = parseModel(payload.model);
	if (!model) throw new Error("Сервер вернул некорректные данные модели.");
	return model;
}

export async function deleteUserModel(modelId: string): Promise<void> {
	if (!SAFE_MODEL_ID.test(modelId)) {
		throw new Error("Некорректный ID модели.");
	}
	await userModelRequest(
		`/api/v3/user-models/${encodeURIComponent(modelId)}`,
		{ method: "DELETE" },
	);
}

export async function testUserModel(
	modelId: string,
): Promise<{ status: string; message: string }> {
	if (!SAFE_MODEL_ID.test(modelId)) {
		throw new Error("Некорректный ID модели.");
	}
	const payload = await userModelRequest(
		`/api/v3/user-models/${encodeURIComponent(modelId)}/test`,
		{ method: "POST" },
	);
	if (!isRecord(payload) || typeof payload.status !== "string") {
		throw new Error("Сервер вернул некорректный ответ.");
	}
	return {
		status: payload.status,
		message:
			typeof payload.message === "string"
				? payload.message
				: "Неизвестный результат.",
	};
}

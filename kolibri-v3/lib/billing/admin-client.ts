import { withCsrfHeader } from "@/lib/csrf";

export type BillingAdminConfigStatus = "disabled" | "configured" | "invalid";
export type BillingAdminConfigSource = "env" | "admin" | "none";
export type BillingAdminMode = "off" | "test" | "demo" | "production" | null;

export type BillingAdminConfig = {
	status: BillingAdminConfigStatus;
	source: BillingAdminConfigSource;
	mode: BillingAdminMode;
	receiptMode: "disabled" | "required" | null;
	productionConfirmed: boolean;
	verifySsl: boolean;
	notificationUrl: string | null;
	returnOrigin: string | null;
	terminalFingerprint: string | null;
	updatedAt: number | null;
};

export type BillingAdminConfigUpdate = {
	enabled: boolean;
	mode: "test" | "demo";
	terminalKey?: string;
	password?: string;
	notificationUrl?: string;
	returnOrigin?: string;
	receiptMode?: "disabled" | "required";
	taxation?: string;
	verifySsl?: boolean;
};

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sanitizeConfig(value: unknown): BillingAdminConfig | null {
	if (
		!isRecord(value) ||
		!["disabled", "configured", "invalid"].includes(String(value.status)) ||
		!["env", "admin", "none"].includes(String(value.source)) ||
		(value.mode !== null &&
			!["off", "test", "demo", "production"].includes(String(value.mode))) ||
		(value.receiptMode !== null &&
			!["disabled", "required"].includes(String(value.receiptMode))) ||
		typeof value.productionConfirmed !== "boolean" ||
		typeof value.verifySsl !== "boolean" ||
		(value.notificationUrl !== null &&
			typeof value.notificationUrl !== "string") ||
		(value.returnOrigin !== null && typeof value.returnOrigin !== "string") ||
		(value.terminalFingerprint !== null &&
			typeof value.terminalFingerprint !== "string") ||
		(value.updatedAt !== null && typeof value.updatedAt !== "number")
	) {
		return null;
	}
	return {
		status: value.status as BillingAdminConfigStatus,
		source: value.source as BillingAdminConfigSource,
		mode: value.mode as BillingAdminMode,
		receiptMode: value.receiptMode as BillingAdminConfig["receiptMode"],
		productionConfirmed: value.productionConfirmed,
		verifySsl: value.verifySsl,
		notificationUrl: value.notificationUrl as string | null,
		returnOrigin: value.returnOrigin as string | null,
		terminalFingerprint: value.terminalFingerprint as string | null,
		updatedAt: value.updatedAt as number | null,
	};
}

export class BillingAdminApiError extends Error {
	readonly code: string;
	readonly status: number;

	constructor(status: number, code: string, message: string) {
		super(message);
		this.name = "BillingAdminApiError";
		this.code = code;
		this.status = status;
	}
}

async function requestConfig(
	init: RequestInit,
): Promise<BillingAdminConfig> {
	const headers = new Headers({ Accept: "application/json", ...init.headers });
	if (init.body) headers.set("Content-Type", "application/json");
	const response = await fetch("/api/superadmin/billing/config", {
		...init,
		headers: withCsrfHeader(headers),
		credentials: "same-origin",
		cache: "no-store",
	});
	let payload: unknown = null;
	try {
		payload = await response.json();
	} catch {
		payload = null;
	}
	if (!response.ok) {
		const detail = isRecord(payload) ? payload.detail : payload;
		const details = isRecord(detail) ? detail : null;
		throw new BillingAdminApiError(
			response.status,
			typeof details?.code === "string" ? details.code : `http_${response.status}`,
			typeof details?.message === "string"
				? details.message
				: "Не удалось сохранить настройки оплаты.",
		);
	}
	const config = sanitizeConfig(payload);
	if (!config) {
		throw new BillingAdminApiError(
			502,
			"billing_config_contract_invalid",
			"Сервис вернул некорректные настройки оплаты.",
		);
	}
	return config;
}

export function getAdminBillingConfig() {
	return requestConfig({ method: "GET" });
}

export function saveAdminBillingConfig(input: BillingAdminConfigUpdate) {
	return requestConfig({
		method: "PUT",
		body: JSON.stringify({
			enabled: input.enabled,
			mode: input.mode,
			terminalKey: input.terminalKey?.trim() || undefined,
			password: input.password?.trim() || undefined,
			notificationUrl: input.notificationUrl?.trim() || undefined,
			returnOrigin: input.returnOrigin?.trim() || undefined,
			receiptMode: input.receiptMode ?? "disabled",
			taxation: input.taxation?.trim() || undefined,
			verifySsl: input.verifySsl ?? true,
		}),
	});
}

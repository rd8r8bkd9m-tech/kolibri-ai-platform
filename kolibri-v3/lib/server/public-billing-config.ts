import "server-only";

export type PublicTbankMode = "off" | "test" | "demo" | "production";

export type PublicTbankStatus =
	| "disabled"
	| "demo"
	| "test"
	| "production"
	| "invalid";

export type PublicTbankConfig = {
	readonly status: PublicTbankStatus;
	readonly mode: PublicTbankMode | null;
	readonly providerReady: boolean;
	readonly productionConfirmed: boolean;
	readonly methodsConfigured: boolean;
	readonly receiptMode: "disabled" | "required" | null;
	readonly readyForLive: boolean;
	readonly label: string;
};

const ALLOWED_MODES: Record<string, PublicTbankMode> = {
	off: "off",
	test: "test",
	demo: "demo",
	production: "production",
};

function parseMode(value: string | undefined): PublicTbankMode | null {
	const normalized = (value ?? "off").trim().toLowerCase();
	return ALLOWED_MODES[normalized] ?? null;
}

function parseBool(value: string | undefined, fallback: boolean): boolean {
	if (value === undefined) return fallback;
	const normalized = value.trim().toLowerCase();
	if (normalized === "" || normalized === "false" || normalized === "0" || normalized === "off" || normalized === "no") {
		return false;
	}
	if (normalized === "true" || normalized === "1" || normalized === "on" || normalized === "yes") {
		return true;
	}
	return fallback;
}

function normalizeReceiptMode(value: string | undefined): "disabled" | "required" | null {
	const normalized = (value ?? "disabled").trim().toLowerCase();
	if (normalized === "disabled" || normalized === "required") {
		return normalized;
	}
	return null;
}

export function getPublicTbankConfig(): PublicTbankConfig {
	const enabled = parseBool(process.env.KOLIBRI_V3_TBANK_ENABLED, false);
	const mode = parseMode(process.env.KOLIBRI_V3_TBANK_MODE);
	const productionConfirmed = parseBool(
		process.env.KOLIBRI_V3_TBANK_PRODUCTION_CONFIRMED,
		false,
	);
	const receiptMode = normalizeReceiptMode(process.env.KOLIBRI_V3_TBANK_RECEIPT_MODE);
	const terminalKey = (process.env.KOLIBRI_V3_TBANK_TERMINAL_KEY ?? "").trim();
	const password = (process.env.KOLIBRI_V3_TBANK_PASSWORD ?? "").trim();
	const callbackUrl = (process.env.KOLIBRI_V3_TBANK_NOTIFICATION_URL ?? "").trim();
	const returnOrigin = (process.env.KOLIBRI_V3_TBANK_RETURN_ORIGIN ?? "").trim();

	if (!enabled) {
		return {
			status: "disabled",
			mode: null,
			providerReady: false,
			productionConfirmed: false,
			methodsConfigured: false,
			receiptMode,
			readyForLive: false,
			label: "Платежный модуль отключен",
		};
	}

	if (!mode || mode === "off") {
		return {
			status: "invalid",
			mode: mode ?? null,
			providerReady: false,
			productionConfirmed: false,
			methodsConfigured: false,
			receiptMode,
			readyForLive: false,
			label: "Неверная конфигурация метода подключения",
		};
	}

	const terminalReady = terminalKey.length > 0 && password.length > 0 && terminalKey.length <= 64;
	const callbackReady = callbackUrl.length > 0 && returnOrigin.length > 0;
	const methodsConfigured = terminalReady && callbackReady;
	const production = mode === "production";

	if (mode === "production" && terminalKey.toUpperCase().endsWith("DEMO")) {
		return {
			status: "invalid",
			mode,
			providerReady: false,
			productionConfirmed,
			methodsConfigured: false,
			receiptMode,
			readyForLive: false,
			label: "Для production нужно non-DEMO терминал",
		};
	}

	if (production && !productionConfirmed) {
		return {
			status: "invalid",
			mode,
			providerReady: methodsConfigured,
			productionConfirmed,
			methodsConfigured,
			receiptMode,
			readyForLive: false,
			label: "Подтверждение real charge не включено",
		};
	}

	return {
		status: mode,
		mode,
		providerReady: methodsConfigured,
		productionConfirmed,
		methodsConfigured,
		receiptMode,
		readyForLive: methodsConfigured && (mode !== "production" || productionConfirmed),
		label:
			mode === "demo"
				? "Демо-режим для тестовых платежей"
				: mode === "test"
				? "Тестовое окружение (не DEMO терминал)"
				: productionConfirmed
				? "Production готов к принятию реальных оплат"
				: "Production включён, но требуется финальное подтверждение",
	};
}


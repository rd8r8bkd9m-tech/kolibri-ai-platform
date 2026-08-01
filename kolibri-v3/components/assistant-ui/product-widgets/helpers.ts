"use client";

import { withCsrfHeader } from "@/lib/csrf";
import { announceAuthenticationRequired } from "@/lib/identity/events";
import {
	type EstimateDraftSnapshot,
} from "@/lib/estimate-version-conflict";
import {
	type EditableEstimateRow,
	type EstimateWidgetProps,
	type ProjectContextSummary,
} from "./types";

export const toAmount = (quantity: string, unitPrice: string) => {
	const left = Number(quantity);
	const right = Number(unitPrice);
	if (!Number.isFinite(left) || !Number.isFinite(right)) return 0;
	return Math.round(left * right * 100) / 100;
};

export const formatMoney = (value: number | string) => {
	const numeric = typeof value === "number" ? value : Number(value);
	return new Intl.NumberFormat("ru-RU", {
		style: "currency",
		currency: "RUB",
		maximumFractionDigits: 2,
	}).format(Number.isFinite(numeric) ? numeric : 0);
};

export const readResponseError = async (response: Response) => {
	if (response.status === 401) announceAuthenticationRequired();
	try {
		const value = (await response.json()) as unknown;
		if (
			typeof value === "object" &&
			value !== null &&
			"message" in value &&
			typeof value.message === "string"
		) {
			return value.message;
		}
	} catch {
		// bounded fallback
	}
	return "Не удалось сохранить смету.";
};

export const emptyRow = (): EditableEstimateRow => ({
	id: `row_${globalThis.crypto.randomUUID().replaceAll("-", "")}`,
	section: "Прочее",
	kind: "service",
	description: "",
	unit: "шт.",
	quantity: "1",
	unitPrice: "0.00",
	quantityBasis: "Введено пользователем",
	priceBasis: "Введено пользователем",
	priceEvidence: null,
});

export const editableRowsFromEstimate = (
	estimate: EstimateWidgetProps,
): EditableEstimateRow[] =>
	estimate.rows.map(({ lineTotal: _lineTotal, ...row }) => row);

export const draftSnapshotFromEstimate = (
	estimate: EstimateWidgetProps,
): EstimateDraftSnapshot => ({
	title: estimate.estimateTitle,
	rows: editableRowsFromEstimate(estimate),
});

export async function loadProjectContextSummary(
	projectId: string,
): Promise<ProjectContextSummary> {
	const response = await fetch(
		`/api/v3/projects/${encodeURIComponent(projectId)}/context`,
		{
			method: "GET",
			headers: { Accept: "application/json" },
			credentials: "same-origin",
			cache: "no-store",
		},
	);
	if (!response.ok) throw new Error(await readResponseError(response));
	const value: unknown = await response.json();
	if (typeof value !== "object" || value === null) {
		throw new Error("Сервер вернул неизвестный контекст проекта.");
	}
	const record = value as Record<string, unknown>;
	const project = record.project;
	const object = record.object;
	const parties = Array.isArray(record.parties) ? record.parties : [];
	if (typeof project !== "object" || project === null) {
		throw new Error("В контексте отсутствует проект.");
	}
	const projectName = (project as Record<string, unknown>).name;
	if (typeof projectName !== "string" || projectName.trim() === "") {
		throw new Error("В контексте отсутствует название проекта.");
	}
	const partySummary = (role: "client" | "contractor") => {
		const party = parties.find(
			(candidate) =>
				typeof candidate === "object" &&
				candidate !== null &&
				(candidate as Record<string, unknown>).role === role &&
				(candidate as Record<string, unknown>).isPrimary === true,
		);
		if (typeof party !== "object" || party === null) return null;
		const value = party as Record<string, unknown>;
		if (
			typeof value.id !== "string" ||
			(value.entityType !== "person" && value.entityType !== "organization") ||
			typeof value.displayName !== "string"
		) {
			return null;
		}
		const entityType = value.entityType as "person" | "organization";
		return {
			id: value.id,
			role,
			entityType,
			displayName: value.displayName,
			taxId: typeof value.taxId === "string" ? value.taxId : null,
			registrationCode:
				typeof value.registrationCode === "string"
					? value.registrationCode
					: null,
		};
	};
	const objectName =
		typeof object === "object" &&
		object !== null &&
		typeof (object as Record<string, unknown>).name === "string"
			? String((object as Record<string, unknown>).name)
			: null;
	return {
		projectName,
		objectName,
		client: partySummary("client"),
		contractor: partySummary("contractor"),
	};
}

export const optionalValue = (value: string) => {
	const normalized = value.trim();
	return normalized === "" ? null : normalized;
};

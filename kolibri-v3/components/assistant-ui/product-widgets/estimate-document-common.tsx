"use client";

import { CheckCircle2Icon, CopyIcon, LoaderCircleIcon } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { withCsrfHeader } from "@/lib/csrf";
import { loadEstimateWindow } from "@/lib/estimate/document";
import { announceDocumentsChanged, openEstimateInWorkspace } from "@/lib/workspace-events";
import {
	EstimateCopyResult,
	type EstimateExportFormat,
	type EstimateWidgetProps,
	type ProjectContextSummary,
	type ProjectPartySummary,
} from "./types";

export const readResponseError = async (response: Response) => {
	if (response.status === 401) {
		return "Необходимо авторизоваться.";
	}
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

export const optionalValue = (value: string) => {
	const normalized = value.trim();
	return normalized === "" ? null : normalized;
};

export type EstimateDocumentIdentity = {
	documentId: string;
	minimumVersion: number;
	projectId: string;
};

export async function loadEstimateDocument({
	documentId,
	minimumVersion,
	projectId,
}: EstimateDocumentIdentity): Promise<EstimateWidgetProps> {
	return loadEstimateWindow({ documentId, minimumVersion, projectId });
}

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
	const partySummary = (
		role: "client" | "contractor",
	): ProjectPartySummary | null => {
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
		return {
			id: value.id,
			role,
			entityType: value.entityType,
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

export async function saveProjectParty(
	projectId: string,
	role: "client" | "contractor",
	payload: {
		displayName: string;
		entityType: "person" | "organization";
		taxId: string | null;
		registrationCode: string | null;
	},
) {
	const response = await fetch(
		`/api/v3/projects/${encodeURIComponent(projectId)}/parties/${role}`,
		{
			method: "PUT",
			headers: withCsrfHeader({
				Accept: "application/json",
				"Content-Type": "application/json",
			}),
			credentials: "same-origin",
			cache: "no-store",
			body: JSON.stringify(payload),
		},
	);
	if (!response.ok) throw new Error(await readResponseError(response));
}

export async function copyEstimateForClient(
	projectId: string,
	idempotencyKey: string,
	payload: {
		projectName: string;
		objectName: string;
		client: {
			displayName: string;
			entityType: "person" | "organization";
			taxId: string | null;
			registrationCode: string | null;
		};
		retainSourceContractor: boolean;
	},
): Promise<EstimateCopyResult> {
	const response = await fetch(
		`/api/v3/projects/${encodeURIComponent(projectId)}/estimate/copies`,
		{
			method: "POST",
			headers: withCsrfHeader({
				Accept: "application/json",
				"Content-Type": "application/json",
				"Idempotency-Key": idempotencyKey,
			}),
			credentials: "same-origin",
			cache: "no-store",
			body: JSON.stringify(payload),
		},
	);
	if (!response.ok) throw new Error(await readResponseError(response));
	const value: unknown = await response.json();
	if (typeof value !== "object" || value === null) {
		throw new Error("Сервер вернул неизвестный результат копирования.");
	}
	const record = value as Record<string, unknown>;
	const project = record.project as Record<string, unknown> | undefined;
	const document = record.document as Record<string, unknown> | undefined;
	const lineage = record.lineage as Record<string, unknown> | undefined;
	if (
		!project ||
		!document ||
		!lineage ||
		typeof project.id !== "string" ||
		typeof project.name !== "string" ||
		typeof project.objectName !== "string" ||
		typeof project.threadId !== "string" ||
		typeof document.id !== "string" ||
		typeof document.version !== "number" ||
		typeof document.contentHash !== "string" ||
		typeof lineage.sourceProjectId !== "string" ||
		typeof lineage.sourceDocumentId !== "string" ||
		typeof lineage.sourceVersion !== "number" ||
		typeof lineage.sourceContentHash !== "string"
	) {
		throw new Error("Сервер вернул неизвестный результат копирования.");
	}
	return {
		project: {
			id: project.id,
			name: project.name,
			objectName: project.objectName,
			threadId: project.threadId,
		},
		document: {
			id: document.id,
			version: document.version,
			contentHash: document.contentHash,
		},
		lineage: {
			sourceProjectId: lineage.sourceProjectId,
			sourceDocumentId: lineage.sourceDocumentId,
			sourceVersion: lineage.sourceVersion,
			sourceContentHash: lineage.sourceContentHash,
		},
	};
}

export function PartyEditor({
	projectId,
	role,
	party,
	onSaved,
}: {
	projectId: string;
	role: "client" | "contractor";
	party: ProjectPartySummary | null;
	onSaved: () => Promise<void>;
}) {
	const [displayName, setDisplayName] = useState(party?.displayName ?? "");
	const [entityType, setEntityType] = useState<"person" | "organization">(
		party?.entityType ?? "organization",
	);
	const [taxId, setTaxId] = useState(party?.taxId ?? "");
	const [registrationCode, setRegistrationCode] = useState(
		party?.registrationCode ?? "",
	);
	const [saving, setSaving] = useState(false);
	const [statusText, setStatusText] = useState("");
	const [saveError, setSaveError] = useState("");
	const label = role === "client" ? "Клиент" : "Подрядчик";

	useEffect(() => {
		setDisplayName(party?.displayName ?? "");
		setEntityType(party?.entityType ?? "organization");
		setTaxId(party?.taxId ?? "");
		setRegistrationCode(party?.registrationCode ?? "");
	}, [party]);

	return (
		<form
			className="rounded-xl border border-border bg-background p-3"
			onSubmit={(event) => {
				event.preventDefault();
				setSaving(true);
				setStatusText("");
				setSaveError("");
				void saveProjectParty(projectId, role, {
					displayName: displayName.trim(),
					entityType,
					taxId: optionalValue(taxId),
					registrationCode:
						entityType === "organization"
							? optionalValue(registrationCode)
							: null,
				})
					.then(onSaved)
					.then(() => setStatusText("Назначение сохранено"))
					.catch((reason: unknown) =>
						setSaveError(
							reason instanceof Error
								? reason.message
								: "Не удалось сохранить участника.",
						),
					)
					.finally(() => setSaving(false));
			}}
		>
			<div className="mb-3 flex items-center justify-between gap-3">
				<div>
					<p className="text-sm font-medium">{label}</p>
					<p className="text-xs text-muted-foreground">
						{party ? "Основной участник проекта" : "Пока не назначен"}
					</p>
				</div>
				{party ? (
					<CheckCircle2Icon
						aria-label="Назначен"
						className="size-4 text-emerald-600"
					/>
				) : null}
			</div>
			<div className="grid gap-2 sm:grid-cols-2">
				<label className="grid gap-1 text-xs text-muted-foreground sm:col-span-2">
					Имя или организация
					<Input
						required
						maxLength={240}
						value={displayName}
						onChange={(event) => setDisplayName(event.target.value)}
						placeholder={
							role === "client" ? "Например, ООО Заказчик" : "ООО Подрядчик"
						}
					/>
				</label>
				<label className="grid gap-1 text-xs text-muted-foreground">
					Тип
					<select
						className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-base min-[960px]:text-sm outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
						value={entityType}
						onChange={(event) =>
							setEntityType(
								event.target.value === "person" ? "person" : "organization",
							)
						}
					>
						<option value="organization">Организация</option>
						<option value="person">Физлицо / ИП</option>
					</select>
				</label>
				<label className="grid gap-1 text-xs text-muted-foreground">
					ИНН, необязательно
					<Input
						inputMode="numeric"
						pattern="(?:[0-9]{10}|[0-9]{12})"
						value={taxId}
						onChange={(event) => setTaxId(event.target.value)}
						placeholder="10 или 12 цифр"
					/>
				</label>
				{entityType === "organization" ? (
					<label className="grid gap-1 text-xs text-muted-foreground">
						КПП, необязательно
						<Input
							inputMode="numeric"
							pattern="[0-9]{9}"
							value={registrationCode}
							onChange={(event) => setRegistrationCode(event.target.value)}
							placeholder="9 цифр"
						/>
					</label>
				) : null}
			</div>
			<div className="mt-3 flex items-center gap-3">
				<Button type="submit" size="sm" disabled={saving}>
					{saving ? (
						<LoaderCircleIcon
							aria-hidden="true"
							className="size-4 animate-spin"
						/>
					) : null}
					{party ? "Обновить" : "Назначить"}
				</Button>
				{saveError ? (
					<p className="text-xs text-destructive" role="alert">
						{saveError}
					</p>
				) : statusText ? (
					<p className="text-xs text-muted-foreground" role="status">
						{statusText}
					</p>
				) : null}
			</div>
		</form>
	);
}

export function ProjectPartiesPanel({
	projectId,
	context,
	onSaved,
}: {
	projectId: string;
	context: ProjectContextSummary;
	onSaved: () => Promise<void>;
}) {
	return (
		<div className="grid gap-3 md:grid-cols-2">
			<PartyEditor
				projectId={projectId}
				role="client"
				party={context.client}
				onSaved={onSaved}
			/>
			<PartyEditor
				projectId={projectId}
				role="contractor"
				party={context.contractor}
				onSaved={onSaved}
			/>
		</div>
	);
}

export function EstimateCopyPanel({
	estimate,
	context,
}: {
	estimate: EstimateWidgetProps;
	context: ProjectContextSummary;
}) {
	const [projectName, setProjectName] = useState(
		`Копия — ${context.projectName}`,
	);
	const [objectName, setObjectName] = useState(
		context.objectName ?? "Объект уточняется",
	);
	const [clientName, setClientName] = useState("");
	const [clientType, setClientType] = useState<"person" | "organization">(
		"organization",
	);
	const [clientTaxId, setClientTaxId] = useState("");
	const [clientRegistrationCode, setClientRegistrationCode] = useState("");
	const [retainContractor, setRetainContractor] = useState(
		context.contractor !== null,
	);
	const [submitting, setSubmitting] = useState(false);
	const [error, setError] = useState("");
	const [result, setResult] = useState<EstimateCopyResult | null>(null);
	const idempotencyKey = useRef<string | null>(null);

	if (result) {
		return (
			<div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-950">
				<div className="flex items-start gap-3">
					<CheckCircle2Icon
						aria-hidden="true"
						className="mt-0.5 size-5 shrink-0"
					/>
					<div className="min-w-0 flex-1">
						<p className="text-sm font-semibold">Создан отдельный проект</p>
						<p className="mt-1 text-sm">
							{result.project.name} · {result.project.objectName}
						</p>
						<p className="mt-1 text-xs opacity-75">
							Источник: версия {result.lineage.sourceVersion} текущей сметы.
							Копия получила собственный документ версии{" "}
							{result.document.version}.
						</p>
						<Button
							type="button"
							size="sm"
							className="mt-3"
							onClick={() =>
								openEstimateInWorkspace({
									documentId: result.document.id,
									projectId: result.project.id,
									title: estimate.estimateTitle,
									version: result.document.version,
									projectName: result.project.name,
								})
							}
						>
							Открыть копию
						</Button>
					</div>
				</div>
			</div>
		);
	}

	return (
		<form
			className="rounded-xl border border-border bg-background p-4"
			onSubmit={(event) => {
				event.preventDefault();
				setSubmitting(true);
				setError("");
				idempotencyKey.current ??= `estimate-copy-${crypto.randomUUID()}`;
				void copyEstimateForClient(estimate.projectId, idempotencyKey.current, {
					projectName: projectName.trim(),
					objectName: objectName.trim(),
					client: {
						displayName: clientName.trim(),
						entityType: clientType,
						taxId: optionalValue(clientTaxId),
						registrationCode:
							clientType === "organization"
								? optionalValue(clientRegistrationCode)
								: null,
					},
					retainSourceContractor: retainContractor,
				})
					.then((value) => {
						setResult(value);
						idempotencyKey.current = null;
						announceDocumentsChanged();
					})
					.catch((reason: unknown) =>
						setError(
							reason instanceof Error
								? reason.message
								: "Не удалось повторить смету.",
						),
					)
					.finally(() => setSubmitting(false));
			}}
		>
			<div className="mb-4">
				<p className="text-sm font-semibold">Повторить для другого клиента</p>
				<p className="mt-1 text-xs text-muted-foreground">
					Будет создан новый проект и новый документ. Исходная смета останется
					неизменной, а связь с её текущей версией сохранится.
				</p>
			</div>
			<div className="grid gap-3 sm:grid-cols-2">
				<label className="grid gap-1 text-xs text-muted-foreground">
					Новый проект
					<Input
						required
						maxLength={240}
						value={projectName}
						onChange={(event) => setProjectName(event.target.value)}
					/>
				</label>
				<label className="grid gap-1 text-xs text-muted-foreground">
					Объект
					<Input
						required
						maxLength={240}
						value={objectName}
						onChange={(event) => setObjectName(event.target.value)}
					/>
				</label>
				<label className="grid gap-1 text-xs text-muted-foreground sm:col-span-2">
					Новый клиент
					<Input
						required
						maxLength={240}
						value={clientName}
						onChange={(event) => setClientName(event.target.value)}
						placeholder="Имя или название организации"
					/>
				</label>
				<label className="grid gap-1 text-xs text-muted-foreground">
					Тип клиента
					<select
						className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-base min-[960px]:text-sm outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
						value={clientType}
						onChange={(event) =>
							setClientType(
								event.target.value === "person" ? "person" : "organization",
							)
						}
					>
						<option value="organization">Организация</option>
						<option value="person">Физлицо / ИП</option>
					</select>
				</label>
				<label className="grid gap-1 text-xs text-muted-foreground">
					ИНН, необязательно
					<Input
						inputMode="numeric"
						pattern="(?:[0-9]{10}|[0-9]{12})"
						value={clientTaxId}
						onChange={(event) => setClientTaxId(event.target.value)}
						placeholder="10 или 12 цифр"
					/>
				</label>
				{clientType === "organization" ? (
					<label className="grid gap-1 text-xs text-muted-foreground">
						КПП, необязательно
						<Input
							inputMode="numeric"
							pattern="[0-9]{9}"
							value={clientRegistrationCode}
							onChange={(event) =>
								setClientRegistrationCode(event.target.value)
							}
							placeholder="9 цифр"
						/>
					</label>
				) : null}
			</div>
			{context.contractor ? (
				<label className="mt-3 flex items-start gap-2 text-sm">
					<input
						type="checkbox"
						className="mt-0.5 size-4 rounded border-input"
						checked={retainContractor}
						onChange={(event) => setRetainContractor(event.target.checked)}
					/>
					<span>
						Оставить подрядчика «{context.contractor.displayName}» в новом
						проекте
					</span>
				</label>
			) : null}
			<div className="mt-4 flex items-center gap-3">
				<Button type="submit" size="sm" disabled={submitting}>
					{submitting ? (
						<LoaderCircleIcon
							aria-hidden="true"
							className="size-4 animate-spin"
						/>
					) : (
						<CopyIcon aria-hidden="true" className="size-4" />
					)}
					Создать отдельный проект
				</Button>
				{error ? (
					<p className="text-xs text-destructive" role="alert">
						{error}
					</p>
				) : null}
			</div>
		</form>
	);
}

export function downloadSavedEstimate(
	projectId: string,
	format: EstimateExportFormat,
) {
	const anchor = document.createElement("a");
	anchor.href = `/api/v3/projects/${encodeURIComponent(projectId)}/estimate/export/${format}`;
	anchor.download = "";
	document.body.append(anchor);
	anchor.click();
	anchor.remove();
}

import { z } from "zod";

const SAFE_PROJECT_ID = /^project_[A-Za-z0-9._~-]{8,96}$/;

export const ESTIMATE_GENERATION_ACTIVITY_ACTORS = [
	"Оркестратор",
	"Технолог",
	"Инженер объёмов",
	"Нормировщик",
	"Исследователь",
	"Снабженец",
	"Логистика",
	"Проверяющий",
] as const;

export const ESTIMATE_GENERATION_ACTIVITY_ROLES = [
	"orchestrator",
	"technologist",
	"quantity_engineer",
	"resource_normer",
	"technical_researcher",
	"procurement",
	"logistics",
	"reviewer",
] as const;

export const ESTIMATE_GENERATION_ACTIVITY_STATUSES = [
	"queued",
	"working",
	"completed",
	"failed",
	"revision_required",
] as const;

type EstimateGenerationActivityRole =
	(typeof ESTIMATE_GENERATION_ACTIVITY_ROLES)[number];

const ACTOR_BY_ROLE: Readonly<
	Record<
		EstimateGenerationActivityRole,
		(typeof ESTIMATE_GENERATION_ACTIVITY_ACTORS)[number]
	>
> = {
	orchestrator: "Оркестратор",
	technologist: "Технолог",
	quantity_engineer: "Инженер объёмов",
	resource_normer: "Нормировщик",
	technical_researcher: "Исследователь",
	procurement: "Снабженец",
	logistics: "Логистика",
	reviewer: "Проверяющий",
};

export const estimateGenerationActivitySchema = z
	.object({
		actor: z.enum(ESTIMATE_GENERATION_ACTIVITY_ACTORS),
		createdAt: z.string().trim().min(1).max(64),
		id: z.string().trim().min(1).max(200),
		message: z.string().trim().min(1).max(500),
		role: z.enum(ESTIMATE_GENERATION_ACTIVITY_ROLES),
		section: z.string().trim().min(1).max(240).nullable(),
		status: z.enum(ESTIMATE_GENERATION_ACTIVITY_STATUSES),
	})
	.strict()
	.refine((value) => value.actor === ACTOR_BY_ROLE[value.role], {
		message: "Estimate generation activity actor and role are inconsistent.",
	});

const progressSchema = z
	.object({
		completed: z.number().int().nonnegative(),
		total: z.number().int().nonnegative(),
	})
	.strict()
	.refine((value) => value.completed <= value.total, {
		message: "Estimate generation progress is inconsistent.",
	});

const statusCountsSchema = z
	.object({
		byStatus: z.record(
			z.string().trim().min(1).max(64),
			z.number().int().nonnegative(),
		),
		total: z.number().int().nonnegative(),
	})
	.strict();

export const estimateGenerationRunSchema = z
	.object({
		cancelRequested: z.boolean(),
		createdAt: z.string().trim().min(1).max(64),
		finishedAt: z.string().trim().min(1).max(64).nullable(),
		id: z.string().regex(/^run_estimate_generation_[0-9a-f]{32}$/),
		lastError: z
			.object({
				code: z.string().trim().min(1).max(500).optional(),
				message: z.string().trim().min(1).max(500).optional(),
			})
			.strict()
			.nullable(),
		progress: progressSchema,
		projectCaseRef: z
			.object({
				id: z.string().trim().min(1).max(160),
				version: z.number().int().nonnegative(),
			})
			.strict(),
		projectId: z.string().regex(SAFE_PROJECT_ID),
		quality: z
			.object({
				errors: z.number().int().nonnegative().optional(),
				warnings: z.number().int().nonnegative().optional(),
			})
			.strict()
			.nullable(),
		qualityStatus: z.enum(["pending", "failed", "passed"]),
		recentActivity: z.array(estimateGenerationActivitySchema).max(12),
		result: z
			.object({
				documentId: z
					.string()
					.regex(/^document_[A-Za-z0-9._~-]{8,96}$/),
				estimateVersion: z.number().int().min(1),
			})
			.strict()
			.nullable(),
		sectionProgress: statusCountsSchema,
		sourceRunId: z
			.string()
			.regex(/^run_[A-Za-z0-9._~-]{8,96}$/)
			.nullable(),
		stage: z.enum([
			"project_case",
			"decomposition",
			"technology",
			"research",
			"pricing",
			"expansion",
			"reconciliation",
			"persisting",
			"complete",
		]),
		status: z.enum([
			"queued",
			"running",
			"needs_input",
			"review",
			"ready",
			"failed",
			"cancelled",
		]),
		taskProgress: statusCountsSchema,
		updatedAt: z.string().trim().min(1).max(64),
	})
	.strict();

const estimateGenerationSummarySchema = z
	.object({
		generationRun: estimateGenerationRunSchema.nullable(),
		projectId: z.string().regex(SAFE_PROJECT_ID),
		schemaVersion: z.literal("1.0"),
	})
	.strict();

export type EstimateGenerationRun = z.infer<
	typeof estimateGenerationRunSchema
>;

export type EstimateGenerationActivity = z.infer<
	typeof estimateGenerationActivitySchema
>;

export type EstimateGenerationSummary = z.infer<
	typeof estimateGenerationSummarySchema
>;

export const ESTIMATE_GENERATION_POLLING_STATUSES = new Set<
	EstimateGenerationRun["status"]
>(["queued", "running", "review"]);

export const ESTIMATE_GENERATION_RECOVERABLE_STATUSES = new Set<
	EstimateGenerationRun["status"]
>(["queued", "running", "review", "needs_input"]);

export function parseEstimateGenerationSummary(
	value: unknown,
	projectId: string,
): EstimateGenerationSummary {
	const parsed = estimateGenerationSummarySchema.safeParse(value);
	if (!parsed.success || parsed.data.projectId !== projectId) {
		throw new Error("Сервер вернул неизвестный статус формирования сметы.");
	}
	return parsed.data;
}

export async function loadLatestEstimateGeneration(
	projectId: string,
	signal?: AbortSignal,
): Promise<EstimateGenerationSummary> {
	if (!SAFE_PROJECT_ID.test(projectId)) {
		throw new Error("Не удалось определить проект для формирования сметы.");
	}
	const response = await fetch(
		`/api/v3/projects/${encodeURIComponent(projectId)}/estimate/generation`,
		{
			method: "GET",
			headers: { Accept: "application/json" },
			credentials: "same-origin",
			cache: "no-store",
			signal,
		},
	);
	if (!response.ok) {
		const error = new Error(
			"Не удалось обновить статус формирования сметы.",
		) as Error & { status?: number };
		error.status = response.status;
		throw error;
	}
	return parseEstimateGenerationSummary(await response.json(), projectId);
}

export function selectEstimateGenerationRun({
	candidate,
	expectedSourceRunId,
	trackedRunId,
}: {
	readonly candidate: EstimateGenerationRun | null;
	readonly expectedSourceRunId: string | null;
	readonly trackedRunId: string | null;
}): EstimateGenerationRun | null {
	if (candidate === null) return null;
	if (candidate.id === trackedRunId) return candidate;
	if (
		expectedSourceRunId !== null &&
		candidate.sourceRunId === expectedSourceRunId
	) {
		return candidate;
	}
	if (trackedRunId !== null || expectedSourceRunId !== null) return null;
	return ESTIMATE_GENERATION_RECOVERABLE_STATUSES.has(candidate.status)
		? candidate
		: null;
}

const STAGE_LABELS: Readonly<
	Record<EstimateGenerationRun["stage"], string>
> = {
	project_case: "Разбираю исходные данные",
	decomposition: "Разбиваю проект на разделы",
	technology: "Строю технологическую карту",
	research: "Проверяю нормы и источники",
	pricing: "Собираю и проверяю цены",
	expansion: "Формирую позиции сметы",
	reconciliation: "Проверяю полноту и итоги",
	persisting: "Сохраняю версию сметы",
	complete: "Смета готова",
};

export function estimateGenerationStatusLabel(run: EstimateGenerationRun) {
	switch (run.status) {
		case "queued":
			return "Смета принята в очередь";
		case "needs_input":
			return "Нужны уточнения для сметы";
		case "review":
			return "Проверяю смету";
		case "ready":
			return "Смета готова в редакторе";
		case "failed":
			return "Не удалось завершить смету";
		case "cancelled":
			return "Формирование сметы отменено";
		default:
			return STAGE_LABELS[run.stage];
	}
}

export function estimateGenerationActivityActor(
	role: EstimateGenerationActivityRole,
) {
	return ACTOR_BY_ROLE[role];
}

export function estimateGenerationProgressLabel(run: EstimateGenerationRun) {
	if (run.progress.total > 0) {
		return `${run.progress.completed} из ${run.progress.total} задач`;
	}
	if (run.taskProgress.total > 0) {
		const completed = ["succeeded", "passed", "completed"].reduce(
			(total, status) => total + (run.taskProgress.byStatus[status] ?? 0),
			0,
		);
		return `${completed} из ${run.taskProgress.total} задач`;
	}
	return null;
}

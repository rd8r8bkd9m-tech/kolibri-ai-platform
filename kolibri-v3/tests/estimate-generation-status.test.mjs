import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const APP_ROOT = path.resolve(
	path.dirname(fileURLToPath(import.meta.url)),
	"..",
);
const read = (relativePath) =>
	readFile(path.join(APP_ROOT, relativePath), "utf8");
const generation = await import(
	pathToFileURL(path.join(APP_ROOT, "lib/estimate/generation.ts")).href
);

const projectId = "project_1234567890abcdef1234567890abcdef";
const sourceRunId = "run_1234567890abcdef1234567890abcdef";
const generationRunId =
	"run_estimate_generation_1234567890abcdef1234567890abcdef";

const generationRun = {
	cancelRequested: false,
	createdAt: "2026-08-02T12:00:00.000Z",
	finishedAt: null,
	id: generationRunId,
	lastError: null,
	progress: { completed: 3, total: 12 },
	projectCaseRef: { id: "project_case_1234567890abcdef", version: 1 },
	projectId,
	quality: null,
	qualityStatus: "pending",
	recentActivity: [
		{
			actor: "Технолог",
			createdAt: "2026-08-02T12:00:04.000Z",
			id: "activity_technology_walls_01",
			message: "Технологическая карта раздела передана на проверку.",
			role: "technologist",
			section: "Стены",
			status: "completed",
		},
	],
	result: null,
	sectionProgress: { byStatus: { active: 2 }, total: 2 },
	sourceRunId,
	stage: "technology",
	status: "running",
	taskProgress: { byStatus: { queued: 9, succeeded: 3 }, total: 12 },
	updatedAt: "2026-08-02T12:00:05.000Z",
};

test("durable generation summaries are bounded and project scoped", () => {
	const parsed = generation.parseEstimateGenerationSummary(
		{
			generationRun,
			projectId,
			schemaVersion: "1.0",
		},
		projectId,
	);
	assert.equal(parsed.generationRun?.id, generationRunId);
	assert.equal(
		generation.estimateGenerationStatusLabel(parsed.generationRun),
		"Строю технологическую карту",
	);
	assert.equal(
		generation.estimateGenerationProgressLabel(parsed.generationRun),
		"3 из 12 задач",
	);
	assert.equal(parsed.generationRun.recentActivity[0].section, "Стены");
	assert.equal(
		generation.estimateGenerationActivityActor("quantity_engineer"),
		"Инженер объёмов",
	);
	assert.deepEqual(
		Object.fromEntries(
			generation.ESTIMATE_GENERATION_ACTIVITY_ROLES.map((role) => [
				role,
				generation.estimateGenerationActivityActor(role),
			]),
		),
		{
			orchestrator: "Оркестратор",
			technologist: "Технолог",
			quantity_engineer: "Инженер объёмов",
			resource_normer: "Нормировщик",
			technical_researcher: "Исследователь",
			procurement: "Снабженец",
			logistics: "Логистика",
			reviewer: "Проверяющий",
		},
	);
	assert.throws(
		() =>
			generation.parseEstimateGenerationSummary(
				{
					generationRun,
					projectId,
					schemaVersion: "1.0",
				},
				"project_abcdefabcdefabcdefabcdefabcd",
			),
		/неизвестный статус/,
	);
});

test("recent activity is bounded, role-consistent, and rejects fabricated fields", () => {
	assert.throws(() =>
		generation.estimateGenerationActivitySchema.parse({
			...generationRun.recentActivity[0],
			actor: "Снабженец",
		}),
	);
	assert.throws(() =>
		generation.estimateGenerationActivitySchema.parse({
			...generationRun.recentActivity[0],
			thought: "hidden reasoning must never cross the contract",
		}),
	);
	assert.throws(() =>
		generation.parseEstimateGenerationSummary(
			{
				generationRun: {
					...generationRun,
					recentActivity: Array.from(
						{ length: 13 },
						(_, index) => ({
							...generationRun.recentActivity[0],
							id: `activity_${index}`,
						}),
					),
				},
				projectId,
				schemaVersion: "1.0",
			},
			projectId,
		),
	);
});

test("only the accepted chat run or an already tracked durable run can drive the editor", () => {
	assert.equal(
		generation.selectEstimateGenerationRun({
			candidate: generationRun,
			expectedSourceRunId: sourceRunId,
			trackedRunId: null,
		})?.id,
		generationRunId,
	);
	assert.equal(
		generation.selectEstimateGenerationRun({
			candidate: generationRun,
			expectedSourceRunId: "run_abcdefabcdefabcdefabcdefabcdefab",
			trackedRunId: null,
		}),
		null,
	);
	assert.equal(
		generation.selectEstimateGenerationRun({
			candidate: generationRun,
			expectedSourceRunId: "run_abcdefabcdefabcdefabcdefabcdefab",
			trackedRunId: generationRunId,
		})?.id,
		generationRunId,
	);
	assert.equal(
		generation.selectEstimateGenerationRun({
			candidate: { ...generationRun, status: "ready" },
			expectedSourceRunId: null,
			trackedRunId: null,
		}),
		null,
		"a historical ready run must not auto-open after an unrelated reload",
	);
});

test("exact brick-house request has a durable live-status and editor handoff regression", async () => {
	const exactPrompt = "Хочу построить кирпичный дом 38 м²";
	const [backendRegression, productRegression, provider, status, screen] =
		await Promise.all([
			read("backend/tests/test_full_estimate_generation.py"),
			read("backend/tests/test_product_widgets.py"),
			read("app/MyRuntimeProvider.tsx"),
			read(
				"components/assistant-ui/product-widgets/estimate-generation-status.tsx",
			),
			read("components/assistant-ui/thread/layouts/thread-screen.tsx"),
		]);

	assert.ok(backendRegression.includes(exactPrompt));
	assert.ok(productRegression.includes(exactPrompt));
	assert.match(provider, /AcceptedProductChatRunContext\.Provider/);
	assert.match(provider, /setAcceptedRun\(\{ acceptedAt: Date\.now\(\), runId, threadId \}\)/);
	assert.match(status, /loadLatestEstimateGeneration/);
	assert.match(status, /selectEstimateGenerationRun/);
	assert.match(status, /data-slot="estimate-generation-activity"/);
	assert.match(status, /item\.actor/);
	assert.match(status, /item\.section/);
	assert.match(status, /item\.message/);
	assert.match(status, /item\.createdAt/);
	assert.match(status, /announceDocumentsChanged\(\)/);
	assert.match(status, /openEstimateInWorkspace\(\{/);
	assert.match(status, /version: run\.result\.estimateVersion/);
	assert.doesNotMatch(status, /Markdown|MarkdownText|JSON\.stringify/);
	assert.match(screen, /<EstimateGenerationStatus \/>/);
});

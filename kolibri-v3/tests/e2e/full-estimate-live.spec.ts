import { randomUUID } from "node:crypto";
import { expect, test, type APIRequestContext } from "@playwright/test";

import {
	analyzeEstimateQuality,
	formatEstimateQualityReport,
} from "../estimate-semantic-quality.mjs";

const LIVE_QA_ENABLED = process.env.KOLIBRI_E2E_LIVE_ESTIMATE === "1";
const MINIMUM_FULL_ESTIMATE_ROWS = 1_000;
const MAXIMUM_ESTIMATE_PAGE_ROWS = 100;
const MAXIMUM_PRESENT_ARGUMENT_BYTES = 32 * 1_024;
const CSRF_COOKIE_NAME =
	process.env.NEXT_PUBLIC_KOLIBRI_V3_CSRF_COOKIE_NAME?.trim() ||
	"kolibri_v3_csrf";

type SseEvent = Record<string, unknown> & {
	type?: string;
	toolCallId?: string;
	toolCallName?: string;
	delta?: string;
};

function parseSseEvents(text: string): SseEvent[] {
	return text
		.split("\n")
		.filter((line) => line.startsWith("data: "))
		.map((line) => JSON.parse(line.slice(6)) as SseEvent);
}

type EstimateRow = Record<string, unknown> & {
	id?: string;
	section?: string;
	kind?: string;
	description?: string;
};

type EstimatePage = Record<string, unknown> & {
	documentId?: string;
	version?: number;
	assumptions?: string[];
	generation?: {
		providerProfile?: string;
		runId?: string;
		estimateGenerationRunId?: string;
		technologyCardRevisionId?: string;
		technologyCardHash?: string;
		qualityStatus?: string;
	};
	pricing?: { totalRows?: number };
	rows?: EstimateRow[];
	rowPage?: {
		offset?: number;
		limit?: number;
		totalRows?: number;
		hasMore?: boolean;
	};
};

async function loadAllEstimateRows(
	request: APIRequestContext,
	projectId: string,
): Promise<{ estimate: EstimatePage; rows: EstimateRow[] }> {
	let offset = 0;
	let expectedTotal: number | null = null;
	let expectedVersion: number | null = null;
	let firstPage: EstimatePage | null = null;
	const rows: EstimateRow[] = [];
	const rowIds = new Set<string>();

	for (let pageIndex = 0; pageIndex < 100_000; pageIndex += 1) {
		const response = await request.get(
			`/api/v3/projects/${projectId}/estimate?offset=${offset}&limit=${MAXIMUM_ESTIMATE_PAGE_ROWS}`,
		);
		expect(response.ok(), await response.text()).toBe(true);
		const page = (await response.json()) as EstimatePage;
		firstPage ??= page;
		const pageRows = page.rows ?? [];
		const rowPage = page.rowPage;

		expect(rowPage, "large estimates require an explicit rowPage contract").toBeTruthy();
		expect(rowPage?.offset).toBe(offset);
		expect(rowPage?.limit).toBeGreaterThan(0);
		expect(rowPage?.limit).toBeLessThanOrEqual(MAXIMUM_ESTIMATE_PAGE_ROWS);
		expect(pageRows.length).toBeLessThanOrEqual(MAXIMUM_ESTIMATE_PAGE_ROWS);
		expect(Number.isInteger(rowPage?.totalRows)).toBe(true);

		expectedTotal ??= rowPage?.totalRows ?? null;
		expectedVersion ??= page.version ?? null;
		expect(rowPage?.totalRows).toBe(expectedTotal);
		expect(page.version).toBe(expectedVersion);

		for (const row of pageRows) {
			expect(row.id).toBeTruthy();
			expect(rowIds.has(String(row.id)), `duplicate paged row id ${row.id}`).toBe(false);
			rowIds.add(String(row.id));
			rows.push(row);
		}

		if (rowPage?.hasMore !== true) break;
		expect(pageRows.length, "hasMore page must advance the cursor").toBeGreaterThan(0);
		offset += pageRows.length;
	}

	expect(firstPage).toBeTruthy();
	expect(rows.length).toBe(expectedTotal);
	return { estimate: firstPage!, rows };
}

async function csrfHeaders(
	request: APIRequestContext,
): Promise<Record<string, string>> {
	const storage = await request.storageState();
	const token = storage.cookies.find(
		(cookie) => cookie.name === CSRF_COOKIE_NAME,
	)?.value;
	expect(
		token,
		`authenticated live QA state must contain ${CSRF_COOKIE_NAME}`,
	).toMatch(/^[A-Za-z0-9_-]{32,512}$/);
	return { "x-csrf-token": token! };
}

test("live GPT or MiMo builds and exports a full nine-storey estimate", async ({
	request,
}) => {
	test.skip(
		!LIVE_QA_ENABLED,
		"Run through npm run test:qa:estimate:live with an external QA storage state.",
	);
	test.setTimeout(30 * 60 * 1_000);

	const catalogResponse = await request.get("/api/v3/models/catalog");
	expect(catalogResponse.ok()).toBe(true);
	const catalog = (await catalogResponse.json()) as {
		profiles?: Array<{ id?: string; available?: boolean }>;
	};
	const liveProfiles = (catalog.profiles ?? []).filter(
		(profile) =>
			profile.available === true &&
			(profile.id === "codex-cli" || profile.id === "mimo-code"),
	);
	expect(
		liveProfiles.length,
		"QA account must have a real GPT or MiMo runtime connection",
	).toBeGreaterThan(0);

	const suffix = randomUUID().replaceAll("-", "");
	const response = await request.post("/api/agui", {
		timeout: 28 * 60 * 1_000,
		data: {
			threadId: `thread_live_full_estimate_${suffix}`,
			runId: `run_live_full_estimate_${suffix}`,
			state: null,
			messages: [
				{
					id: `message_live_full_estimate_${suffix}`,
					role: "user",
					content:
						"Составь полную подробную ресурсную смету строительства девятиэтажного монолитного жилого дома на 72 квартиры общей площадью 6200 м² в Казани, от подготовки площадки и нулевого цикла до ввода в эксплуатацию. Включи конструктив, фасад, кровлю, отделку мест общего пользования и квартир, электрику, слаботочные системы, ВК, отопление, вентиляцию, лифты, наружные сети, благоустройство, временные работы, логистику, испытания и пусконаладку. Работы, материалы, оборудование и услуги укажи отдельными строками. Не ограничивай количество позиций; неизвестные исходные данные явно пометь как допущения.",
				},
			],
			tools: [],
			context: [],
			forwardedProps: {
				agentProfile: "auto",
				executionMode: "standard",
				accessMode: "standard",
			},
		},
	});
	expect(response.status(), await response.text()).toBe(200);
	const events = parseSseEvents(await response.text());
	const terminal = events.at(-1);
	expect(terminal?.type, JSON.stringify(terminal)).toBe("RUN_FINISHED");
	expect(terminal?.outcome).toEqual({ type: "success" });

	const presentStart = events.find(
		(event) => event.type === "TOOL_CALL_START" && event.toolCallName === "present",
	);
	expect(presentStart?.toolCallId).toBeTruthy();
	const presentJson = events
		.filter(
			(event) =>
				event.type === "TOOL_CALL_ARGS" &&
				event.toolCallId === presentStart?.toolCallId,
		)
		.map((event) => String(event.delta ?? ""))
		.join("");
	const presented = JSON.parse(presentJson) as {
		$type?: string;
		projectId?: string;
		documentId?: string;
		version?: number;
		rows?: unknown[];
		rowPage?: {
			offset?: number;
			limit?: number;
			totalRows?: number;
			hasMore?: boolean;
		};
	};
	expect(presented.$type).toBe("EstimateEditor");
	expect(presented.projectId).toMatch(/^project_[A-Za-z0-9._~-]{8,96}$/);
	expect(presented.documentId).toMatch(/^document_[A-Za-z0-9._~-]{8,96}$/);
	expect(presented.version).toBeGreaterThanOrEqual(1);
	expect(presented.rows ?? []).toHaveLength(0);
	expect(presented.rowPage?.offset).toBe(0);
	expect(presented.rowPage?.limit).toBe(0);
	expect(presented.rowPage?.totalRows).toBeGreaterThanOrEqual(
		MINIMUM_FULL_ESTIMATE_ROWS,
	);
	expect(presented.rowPage?.hasMore).toBe(true);
	expect(
		Buffer.byteLength(presentJson, "utf8"),
		"chat must contain a compact estimate reference, not the row snapshot",
	).toBeLessThanOrEqual(MAXIMUM_PRESENT_ARGUMENT_BYTES);

	const { estimate, rows } = await loadAllEstimateRows(
		request,
		presented.projectId!,
	);
	expect(rows.length).toBeGreaterThanOrEqual(MINIMUM_FULL_ESTIMATE_ROWS);
	expect(estimate.pricing?.totalRows).toBe(rows.length);
	expect(estimate.assumptions?.length ?? 0).toBeGreaterThan(0);
	expect(["codex-cli", "mimo-code"]).toContain(
		estimate.generation?.providerProfile,
	);
	expect(estimate.generation?.runId).toMatch(
		/^(?:run|calculation)_[A-Za-z0-9._~-]{8,96}$/,
	);
	expect(estimate.generation?.estimateGenerationRunId).toMatch(
		/^run_estimate_generation_[A-Za-z0-9._~-]{8,96}$/,
	);
	expect(estimate.generation?.technologyCardRevisionId).toMatch(
		/^technology_card_revision_[A-Za-z0-9._~-]{8,96}$/,
	);
	expect(estimate.generation?.technologyCardHash).toMatch(/^sha256:[0-9a-f]{64}$/);
	expect(estimate.generation?.qualityStatus).toBe("passed");

	const generationResponse = await request.get(
		`/api/v3/projects/${presented.projectId}/estimate/generation/${estimate.generation?.estimateGenerationRunId}`,
	);
	expect(generationResponse.ok(), await generationResponse.text()).toBe(true);
	const generationSummary = (await generationResponse.json()) as {
		generationRun?: {
			id?: string;
			projectId?: string;
			status?: string;
			stage?: string;
			qualityStatus?: string;
			result?: { documentId?: string; estimateVersion?: number };
			sectionProgress?: { total?: number; byStatus?: Record<string, number> };
			taskProgress?: { total?: number; byStatus?: Record<string, number> };
		};
	};
	const durableRun = generationSummary.generationRun;
	expect(durableRun?.id).toBe(estimate.generation?.estimateGenerationRunId);
	expect(durableRun?.projectId).toBe(presented.projectId);
	expect(durableRun?.status).toBe("ready");
	expect(durableRun?.stage).toBe("complete");
	expect(durableRun?.qualityStatus).toBe("passed");
	expect(durableRun?.result).toEqual({
		documentId: presented.documentId,
		estimateVersion: presented.version,
	});
	expect(durableRun?.sectionProgress?.byStatus?.passed).toBeGreaterThanOrEqual(15);
	expect(durableRun?.taskProgress?.byStatus?.succeeded).toBeGreaterThanOrEqual(
		15 * 7,
	);

	const cardResponse = await request.get(
		`/api/v3/projects/${presented.projectId}/estimate/generation/technology-card/latest`,
	);
	expect(cardResponse.ok(), await cardResponse.text()).toBe(true);
	const cardBody = (await cardResponse.json()) as {
		technologyCardRevision?: {
			id?: string;
			status?: string;
			publishedTechnologyCardId?: string;
			contentHash?: string;
			validationStatus?: string;
			snapshot?: {
				sections?: unknown[];
				operations?: Array<{ resources?: unknown[] }>;
			};
		};
	};
	const card = cardBody.technologyCardRevision;
	expect(card?.id).toBe(estimate.generation?.technologyCardRevisionId);
	expect(card?.status).toBe("accepted");
	expect(card?.publishedTechnologyCardId).toMatch(
		/^technology_card_[A-Za-z0-9._~-]{8,96}$/,
	);
	expect(card?.contentHash).toBe(estimate.generation?.technologyCardHash);
	expect(card?.validationStatus).toBe("passed");
	expect(card?.snapshot?.sections?.length).toBeGreaterThanOrEqual(15);
	expect(card?.snapshot?.operations?.length).toBeGreaterThanOrEqual(15);
	const cardResourceCount = (card?.snapshot?.operations ?? []).reduce(
		(total, operation) => total + (operation.resources?.length ?? 0),
		0,
	);
	expect(cardResourceCount).toBe(rows.length);

	const quality = analyzeEstimateQuality(rows, {
		minimumRows: MINIMUM_FULL_ESTIMATE_ROWS,
		minimumSections: 15,
	});
	await test.info().attach("estimate-semantic-quality.json", {
		body: Buffer.from(formatEstimateQualityReport(quality)),
		contentType: "application/json",
	});
	expect(quality.errors, formatEstimateQualityReport(quality)).toEqual([]);

	const exportResponse = await request.get(
		`/api/v3/projects/${presented.projectId}/estimate/export/csv`,
	);
	expect(exportResponse.ok()).toBe(true);
	const csv = await exportResponse.text();
	for (const row of rows.filter((_, index) => index % 100 === 0)) {
		expect(csv).toContain(String(row.description));
	}

	for (const format of ["xlsx", "pdf"] as const) {
		const exported = await request.get(
			`/api/v3/projects/${presented.projectId}/estimate/export/${format}`,
		);
		expect(
			exported.ok(),
			`${format} export failed with HTTP ${exported.status()}`,
		).toBe(true);
		expect((await exported.body()).byteLength).toBeGreaterThan(1_024);
	}

	const firstRow = rows[0];
	expect(firstRow, "the generated estimate must have an editable first row").toBeTruthy();
	const {
		lineTotal: _lineTotal,
		priceEvidence: _priceEvidence,
		enginePriceProvenance: _enginePriceProvenance,
		...rowUpsert
	} = firstRow;
	void _lineTotal;
	void _priceEvidence;
	void _enginePriceProvenance;
	const editedDescription = `${String(firstRow.description).slice(0, 260)} — QA delta`;
	const originalVersion = estimate.version!;
	const mutation = {
		version: originalVersion,
		upsertRows: [{ ...rowUpsert, description: editedDescription }],
		deleteRowIds: [],
		returnPage: { offset: 0, limit: MAXIMUM_ESTIMATE_PAGE_ROWS },
	};
	const headers = await csrfHeaders(request);
	const editResponse = await request.patch(
		`/api/v3/projects/${presented.projectId}/estimate/rows`,
		{ data: mutation, headers },
	);
	const editedPage = (await editResponse.json()) as EstimatePage;
	expect(editResponse.ok(), JSON.stringify(editedPage)).toBe(true);
	expect(editedPage.version).toBe(originalVersion + 1);
	expect(editedPage.rowPage?.limit).toBe(MAXIMUM_ESTIMATE_PAGE_ROWS);

	const reloadedResponse = await request.get(
		`/api/v3/projects/${presented.projectId}/estimate?offset=0&limit=${MAXIMUM_ESTIMATE_PAGE_ROWS}`,
	);
	expect(reloadedResponse.ok(), await reloadedResponse.text()).toBe(true);
	const reloaded = (await reloadedResponse.json()) as EstimatePage;
	expect(reloaded.version).toBe(originalVersion + 1);
	expect(
		reloaded.rows?.find((row) => row.id === firstRow.id)?.description,
	).toBe(editedDescription);

	const staleResponse = await request.patch(
		`/api/v3/projects/${presented.projectId}/estimate/rows`,
		{ data: mutation, headers },
	);
	expect(staleResponse.status()).toBe(409);
	const stalePayload = (await staleResponse.json()) as Record<string, unknown>;
	expect(JSON.stringify(stalePayload)).toContain("estimate_version_conflict");
});

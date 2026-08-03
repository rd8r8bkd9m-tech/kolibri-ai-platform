import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const APP_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

const readSource = (relativePath) =>
  readFile(path.join(APP_ROOT, relativePath), "utf8");

test("Generative UI uses the official assistant-ui renderer, schema, instance, and escaped serializer", async () => {
  const [library, renderer] = await Promise.all([
    readSource("components/assistant-ui/generative-ui-library.tsx"),
    readSource("components/assistant-ui/generative-ui-renderer.tsx"),
  ]);

  for (const officialApi of [
    "JSONGenerativeUI",
    "buildPresentParameters",
    "renderGenerativeUI",
    "generativeUIToJSX",
  ]) {
    assert.ok(library.includes(officialApi), `missing ${officialApi}`);
  }

  assert.match(library, /new JSONGenerativeUI\s*\(\s*\{/);
  assert.match(library, /\.present\s*\(\s*\)/);
  assert.match(library, /escape:\s*true/);
  assert.match(library, /pretty:\s*true/);
  assert.match(renderer, /sanitizeKolibriGenerativeUI\s*\(\s*spec\s*\)/);
  assert.match(renderer, /renderGenerativeUI\s*\(\s*\n?\s*validation\.value/);
  assert.match(renderer, /export function KolibriGenerativeUI\s*\(/);
  assert.match(renderer, /\bnode:\s*unknown/);
  assert.match(renderer, /\binspectable\?:\s*boolean/);
  assert.match(renderer, /Представление ИИ · не является подтверждением/);
  assert.match(renderer, /kolibri-generative-ui-provenance/);
  assert.ok(
    renderer.indexOf("sanitizeKolibriGenerativeUI(spec)") <
      renderer.indexOf("renderGenerativeUI(\n"),
    "the tree must be sanitized before the official renderer sees it",
  );
});

test("the Kolibri vocabulary is display-only and explicitly allowlisted", async () => {
  const [schema, library] = await Promise.all([
    readSource("lib/generative-ui/schema.ts"),
    readSource("components/assistant-ui/generative-ui-library.tsx"),
  ]);

  for (const component of [
    "Card",
    "Stack",
    "Grid",
    "Heading",
    "Text",
    "Badge",
    "Metric",
    "KeyValue",
    "Progress",
    "Divider",
  ]) {
    assert.match(schema, new RegExp(`\\b${component}:\\s*z`));
    assert.match(library, new RegExp(`\\b${component}:\\s*\\{`));
  }

  assert.doesNotMatch(library, /dangerouslySetInnerHTML/);
  assert.doesNotMatch(library, /<(?:a|button|input|select|textarea)\b/i);
  assert.doesNotMatch(library, /\bonClick\s*=/);
  assert.doesNotMatch(library, /\bhref\s*=/);
  assert.doesNotMatch(library, /\bsrc\s*=/);
});

test("untrusted trees are bounded, schema-validated, and soft-fail accessibly", async () => {
  const [schema, sanitizer, renderer, library] = await Promise.all([
    readSource("lib/generative-ui/schema.ts"),
    readSource("lib/generative-ui/sanitize.ts"),
    readSource("components/assistant-ui/generative-ui-renderer.tsx"),
    readSource("components/assistant-ui/generative-ui-library.tsx"),
  ]);

  for (const limit of [
    "maxDepth",
    "maxNodes",
    "maxChildrenPerNode",
    "maxTextLength",
    "maxTotalTextLength",
    "maxPropStringLength",
  ]) {
    assert.ok(schema.includes(limit), `missing safety limit: ${limit}`);
  }

  for (const guard of [
    "__proto__",
    "prototype",
    "constructor",
    "dangerouslySetInnerHTML",
    "className",
    "style",
    "href",
    "src",
    "formAction",
    "WeakSet",
    "Number.isFinite",
    "safeParse",
    "Reflect.ownKeys",
  ]) {
    assert.ok(sanitizer.includes(guard), `missing sanitizer guard: ${guard}`);
  }

  assert.match(sanitizer, /\^on\/i/);
  assert.match(
    sanitizer,
    /key !== "length"[\s\S]{0,220}descriptor\.get !== undefined[\s\S]{0,80}descriptor\.set !== undefined/,
  );
  assert.match(renderer, /role=["']status["']/);
  assert.match(renderer, /aria-live=["']polite["']/);
  assert.match(library, /Формат интерфейса не поддерживается/);
  assert.match(renderer, /inspectSource\s*=\s*false/);
  assert.match(renderer, /Структура блока/);
  const engineProvenanceBlock =
    schema.match(
      /enginePriceProvenance:[\s\S]*?\.strict\(\)\s*\.optional\(\)/,
    )?.[0] ?? "";
  assert.match(engineProvenanceBlock, /sourceUrl:/);
  assert.doesNotMatch(engineProvenanceBlock, /\n\s*url:/);
});

test("assistant-ui native component specs are converted and validated before use", async () => {
  const sanitizer = await readSource("lib/generative-ui/sanitize.ts");

  assert.match(
    sanitizer,
    /export function parseNativeKolibriGenerativeUI\s*\(/,
  );
  assert.match(sanitizer, /\["component", "props", "children", "key"\]/);
  assert.match(sanitizer, /input\["type"\]\s*===\s*"generative-ui"/);
  assert.match(sanitizer, /sanitizeKolibriGenerativeUI\s*\(\s*canonicalizeNativeNode/);
});

test("estimate widgets accept complete technology assumptions from the backend contract", async () => {
  const { kolibriGenerativeUIComponentSchemas } = await import(
    "../lib/generative-ui/schema.ts"
  );
  const technologyAssumption =
    "Estimate Engine должен сохранить обязательные технологические этапы: " +
    "обследование, очистка, защита, грунт, маяки, углы и сетка по условиям, " +
    "смесь, нанесение, вода, электричество, штукатурная станция, доставка, " +
    "подъём, откосы по условиям, финишное сглаживание, контроль качества, " +
    "уборка, вывоз и расходники.";

  assert.ok(technologyAssumption.length > 300);
  assert.ok(technologyAssumption.length <= 600);

  const result =
    kolibriGenerativeUIComponentSchemas.EstimateEditor.safeParse({
      schemaId: "kolibri.estimate_draft",
      schemaVersion: "1.2",
      projectId: "project_contract_12345678",
      documentId: "document_contract_12345678",
      version: 1,
      status: "draft",
      estimateTitle: "Механизированная штукатурка",
      currency: "RUB",
      estimateRegion: "Республика Татарстан",
      assumptions: [technologyAssumption],
      generation: {
        providerProfile: "estimate-engine",
        runId: "calculation_contract_12345678",
      },
      rows: [],
      pricing: {
        status: "unpriced",
        sourcedRows: 0,
        staleRows: 0,
        totalRows: 0,
        lastCheckedAt: null,
      },
      totals: {
        subtotal: "0.00",
        total: "0.00",
      },
      updatedAt: "2026-07-29T08:00:00Z",
    });

  assert.equal(
    result.success,
    true,
    result.success ? undefined : JSON.stringify(result.error.issues),
  );
});

test("estimate widgets accept provider-neutral server revision profiles", async () => {
  const { kolibriGenerativeUIComponentSchemas } = await import(
    "../lib/generative-ui/schema.ts"
  );

  const result =
    kolibriGenerativeUIComponentSchemas.EstimateEditor.safeParse({
      schemaId: "kolibri.estimate_draft",
      schemaVersion: "1.2",
      projectId: "project_contract_12345678",
      documentId: "document_contract_12345678",
      version: 3,
      status: "draft",
      estimateTitle: "Смета после уточнения",
      currency: "RUB",
      estimateRegion: "Республика Татарстан",
      assumptions: [],
      generation: {
        providerProfile: "server-estimate-revision",
        runId: "run_contract_12345678",
      },
      rows: [],
      pricing: {
        status: "unpriced",
        sourcedRows: 0,
        staleRows: 0,
        totalRows: 0,
        lastCheckedAt: null,
      },
      totals: { subtotal: "0.00", total: "0.00" },
      updatedAt: "2026-07-31T00:00:00Z",
    });

  assert.equal(
    result.success,
    true,
    result.success ? undefined : JSON.stringify(result.error.issues),
  );
});

test("large estimates use a compact reference, bounded row windows, and delta saves", async () => {
	const [{ kolibriGenerativeUIComponentSchemas }, editor, client, route] =
		await Promise.all([
			import("../lib/generative-ui/schema.ts"),
			readSource("components/assistant-ui/product-widgets/estimate-editor.tsx"),
			readSource("lib/estimate/document.ts"),
			readSource("app/api/v3/projects/[projectId]/estimate/rows/route.ts"),
		]);
	const reference = {
		schemaId: "kolibri.estimate_draft",
		schemaVersion: "1.4",
		projectId: "project_contract_12345678",
		documentId: "document_contract_12345678",
		version: 7,
		status: "ready",
		estimateTitle: "Девятиэтажный жилой дом",
		currency: "RUB",
		estimateRegion: "Москва",
		assumptions: [],
		rows: [],
		rowPage: { offset: 0, limit: 0, totalRows: 10_000, hasMore: true },
		pricing: {
			status: "partially_sourced",
			sourcedRows: 8_500,
			staleRows: 0,
			totalRows: 10_000,
			lastCheckedAt: "2026-08-02T10:00:00Z",
		},
		totals: { subtotal: "1200000000.00", total: "1440000000.00" },
		updatedAt: "2026-08-02T10:00:00Z",
	};
	assert.equal(
		kolibriGenerativeUIComponentSchemas.EstimateEditor.safeParse(reference).success,
		true,
	);
	const paged = kolibriGenerativeUIComponentSchemas.EstimateEditor.parse({
		...reference,
		generation: {
			providerProfile: "codex-cli",
			runId: "run_contract_12345678",
			estimateGenerationRunId: "estimate_generation_run_contract_12345678",
			technologyCardRevisionId: "technology_card_revision_contract_12345678",
			technologyCardHash:
				"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			qualityStatus: "passed",
		},
		rows: [
			{
				id: "row_contract_12345678",
				section: "Фундамент",
				kind: "work",
				description: "Устройство монолитной плиты",
				unit: "м3",
				quantity: "12.5",
				unitPrice: "25000.00",
				lineTotal: "312500.00",
				quantityBasis: "По рабочей документации",
				priceBasis: "Предложение поставщика",
				operationId: "operation_foundation_01",
				resourceId: "resource_concrete_01",
				evidenceId: "evidence_quote_01",
				technologyCardVersion: "technology_card_01_v3",
				wbsPath: "01/01.02/01.02.03",
				specification: "Бетон B25 W8 F150",
				quantityFormula: "foundation_area_m2 * slab_thickness_m",
				lineConfidence: "verified",
			},
		],
		rowPage: { offset: 0, limit: 100, totalRows: 10_000, hasMore: true },
	});
	assert.equal(paged.rows[0].quantityFormula, "foundation_area_m2 * slab_thickness_m");
	assert.equal(
		paged.generation?.estimateGenerationRunId,
		"estimate_generation_run_contract_12345678",
	);
	assert.equal(
		kolibriGenerativeUIComponentSchemas.EstimateEditor.safeParse({
			...reference,
			rows: [
				{
					id: "row_contract_12345678",
					section: "Каркас",
					kind: "overhead",
					description: "Накладные расходы",
					unit: "%",
					quantity: "1",
					unitPrice: "1.00",
					lineTotal: "1.00",
					quantityBasis: "Расчёт сервера",
					priceBasis: "Политика проекта",
					lineConfidence: "verified",
				},
			],
		}).success,
		false,
	);
	assert.match(client, /upsertRows/);
	assert.match(client, /deleteRowIds/);
	assert.match(client, /returnPage/);
	assert.match(client, /delta\.upsertRows\.length === 0/);
	assert.match(client, /return loadEstimateWindow/);
	assert.match(editor, /loadEstimateWindow/);
	assert.match(editor, /saveEstimateRowDelta/);
	assert.doesNotMatch(editor, /method:\s*"PATCH"[\s\S]{0,500}currency:[\s\S]{0,100}rows:/);
	assert.match(route, /maxRequestBytes:\s*256 \* 1_024/);
});

test("document-pack preview reports 10000+ lines without embedding them all", async () => {
	const { kolibriGenerativeUIComponentSchemas } = await import(
		"../lib/generative-ui/schema.ts"
	);
	const result = kolibriGenerativeUIComponentSchemas.EstimateDocumentPack.safeParse({
		schemaId: "kolibri.estimate-document-pack",
		schemaVersion: "1.0",
		projectId: "project_contract_12345678",
		estimateVersion: 7,
		status: "preliminary",
		rendererVersion: "estimate-docs-v1",
		requiredFields: [],
		files: [],
		preview: {
			title: "Смета",
			objectName: "Жилой дом",
			region: "Москва",
			date: "2026-08-02",
			validUntil: "2026-09-01",
			number: "КС-7",
			status: "preliminary",
			mode: "preliminary",
			customerName: null,
			contractorName: null,
			sections: [],
			lines: [],
			totalLines: 12_480,
			truncated: true,
			directTotal: "1200000000.00",
			reserve: "0.00",
			tax: "240000000.00",
			total: "1440000000.00",
			totalWords: "Один миллиард четыреста сорок миллионов рублей",
			taxMode: "НДС включён",
			conditions: [],
			exclusions: [],
			paymentSchedule: [],
		},
	});
	assert.equal(result.success, true);
});

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
    readSource("lib/generative-ui/library.tsx"),
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
  assert.match(renderer, /renderGenerativeUI\s*\(\s*validation\.value/);
  assert.match(renderer, /export function KolibriGenerativeUI\s*\(/);
  assert.match(renderer, /\bnode:\s*unknown/);
  assert.match(renderer, /\binspectable\?:\s*boolean/);
  assert.match(renderer, /Представление ИИ · не является подтверждением/);
  assert.match(renderer, /kolibri-generative-ui-provenance/);
  assert.ok(
    renderer.indexOf("sanitizeKolibriGenerativeUI(spec)") <
      renderer.indexOf("renderGenerativeUI(validation.value"),
    "the tree must be sanitized before the official renderer sees it",
  );
});

test("the Kolibri vocabulary is display-only and explicitly allowlisted", async () => {
  const [schema, library] = await Promise.all([
    readSource("lib/generative-ui/schema.ts"),
    readSource("lib/generative-ui/library.tsx"),
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
    readSource("lib/generative-ui/library.tsx"),
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

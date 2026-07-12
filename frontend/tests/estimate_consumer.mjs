import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const vite = await createServer({
  root: fileURLToPath(new URL("..", import.meta.url)),
  server: { middlewareMode: true },
  appType: "custom",
  logLevel: "silent",
});
const {
  calculateEstimateTotals,
  formatEstimateMoney,
  normalizeEstimatePayload,
  priceInputToMinor,
  validEstimateQuantity,
} = await vite.ssrLoadModule("/src/estimate/estimateModel.js");
await vite.close();

const canonical = normalizeEstimatePayload({
  title: "Дом 100 м²",
  currency: "RUB",
  minor_unit: 2,
  region: "Республика Татарстан, Лениногорск",
  sections: [
    {
      id: "foundation",
      name: "Фундамент",
      items: [
        {
          id: "work-1",
          name: "Разработка грунта",
          type: "work",
          unit: "м³",
          quantity: "10",
          unit_price: "123.45",
          total: "1.00",
          source: {
            title: "Текущий прайс поставщика",
            url: "https://prices.example/work-1",
            date: "2026-07-11",
            status: "unverified",
            quote: "Диапазон 120–130 руб.",
          },
          range: { min: "120.00", max: "130.00" },
        },
        {
          id: "material-1",
          name: "Щебень",
          type: "material",
          unit: "т",
          quantity: "2.5",
          unit_price: "100.00",
          total: "999999.00",
          source_ref: "Каталог материалов",
          source_url: "https://prices.example/material-1",
          source_date: "2026-07-10",
          source_status: "unverified",
        },
      ],
    },
  ],
  assumptions: ["Объёмы требуют сверки по проекту"],
  artifacts: [{
    id: "pdf-1",
    status: "materialized",
    kind: "pdf",
    deliverable_type: "pdf",
    media_type: "application/pdf",
    locator: "/v1/public/estimate-artifacts/pdf-1/content",
  }],
});

assert.equal(canonical.lines.length, 2);
assert.equal(canonical.lines[0].section, "Фундамент");
assert.equal(canonical.lines[0].category, "labor");
assert.equal(canonical.lines[0].unitPriceMinor, 12_345);
assert.equal(canonical.lines[0].evidence.priceMinMinor, 12_000);
assert.equal(canonical.lines[0].evidence.priceMaxMinor, 13_000);
assert.equal(canonical.lines[1].category, "material");
assert.equal(canonical.assumptions.length, 1);
assert.equal(canonical.pdfArtifact.id, "pdf-1");

const totals = calculateEstimateTotals(canonical.lines, {
  minorUnit: canonical.minorUnit,
  overheadRateBps: 750,
  taxRateBps: 2_000,
});
assert.equal(totals.lineTotals.get("work-1"), 123_450n);
assert.equal(totals.lineTotals.get("material-1"), 25_000n);
assert.equal(totals.subtotalMinor, 148_450n);
assert.equal(totals.overheadMinor, 11_134n);
assert.equal(totals.taxMinor, 31_917n);
assert.equal(totals.grandTotalMinor, 191_501n);
assert.equal(formatEstimateMoney(totals.grandTotalMinor, 2, "RUB"), "1\u00a0915,01\u00a0₽");

const flat = normalizeEstimatePayload({
  task: {
    result: {
      type: "deterministic_estimate",
      status: "preliminary",
      estimate: {
        title: "Текущие цены",
        currency: "RUB",
        minor_unit: 2,
        region: "Лениногорск",
        lines: [{
          id: "line-current",
          section: "Стены",
          description: "Газобетон",
          category: "material",
          unit: "м³",
          quantity: "12.5",
          unit_price_minor: 712_500,
          provenance: {
            source: "supplier",
            source_ref: "Прайс производителя",
            source_url: "https://supplier.example/aerated",
            captured_at: "2026-07-11",
            price_level_date: "2026-07-11",
            validation_status: "unverified",
          },
        }],
      },
      price_research: {
        schema_version: "kolibri.estimate-price-research.v1",
        lines: [{
          line_id: "line-current",
          price_min_minor: 700_000,
          price_max_minor: 725_000,
          selected_unit_price_minor: 712_500,
          selection_rule: "range_midpoint_round_half_up",
          source_quote: "7 000–7 250 руб./м³",
          source_title: "Прайс производителя",
          source_host: "supplier.example",
          source_retrieved_at: "2026-07-11T08:00:00Z",
        }],
      },
      verification: {
        status: "preliminary",
        source_coverage_complete: true,
      },
    },
  },
});

assert.equal(flat.lines[0].price, "7125.00");
assert.equal(flat.lines[0].evidence.priceMinMinor, 700_000);
assert.equal(flat.lines[0].evidence.priceMaxMinor, 725_000);
assert.equal(flat.lines[0].evidence.selectionRule, "range_midpoint_round_half_up");
assert.match(flat.confidenceLabel, /1 из 1/);

const modelDraft = normalizeEstimatePayload({
  task: {
    result: {
      type: "deterministic_estimate",
      status: "preliminary",
      estimate: {
        title: "Дом 100 м²",
        currency: "RUB",
        minor_unit: 2,
        region: "Лениногорск",
        lines: [{
          id: "model-line",
          section: "Фундамент",
          description: "Устройство фундамента",
          category: "labor",
          unit: "м³",
          quantity: "20",
          unit_price_minor: 650_000,
          provenance: {
            source: "assumption",
            source_ref: "Предварительная оценка основной модели Kolibri",
            validation_status: "unverified",
          },
        }],
      },
    },
  },
});
assert.equal(modelDraft.lines.length, 1);
assert.equal(modelDraft.confidenceLabel, "Цены модели · требуют проверки");

assert.equal(priceInputToMinor("12.345", 2), 1_235);
assert.equal(priceInputToMinor("-1", 2), null);
assert.equal(validEstimateQuantity("0.000001"), true);
assert.equal(validEstimateQuantity("0"), false);

const css = readFileSync(new URL("../src/App.css", import.meta.url), "utf8");
const editor = readFileSync(new URL("../src/windows/EstimateWorkspace.jsx", import.meta.url), "utf8");
const mobileCss = css.slice(css.indexOf("@media (max-width: 760px)"));
assert.match(css, /\.estimate-row button\s*\{[^}]*width:\s*44px[^}]*height:\s*44px/s);
assert.match(mobileCss, /\.estimate-line-total\s*\{[^}]*grid-column:\s*1 \/ 4[^}]*grid-row:\s*4/s);
assert.match(editor, /className="estimate-number-input"[\s\S]*inputMode="decimal"[\s\S]*type="text"/);
assert.doesNotMatch(editor, /className="estimate-number-input"[\s\S]{0,160}type="number"/);

console.log("Kolibri priced estimate consumer contracts passed");

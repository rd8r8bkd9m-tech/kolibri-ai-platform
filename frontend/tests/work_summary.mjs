import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

import { normalizeWorkSummary } from "../src/runtime/kolibriApi.js";

const encoded = JSON.stringify({
  v: 1,
  mode: "summary_only",
  items: [
    { kind: "plan", status: "passed", detail: "Ответ подготовлен." },
    { kind: "tool", status: "passed", detail: "Выполнено: Веб-поиск." },
    { kind: "source", status: "passed", detail: "Проверено источников: 2." },
    { kind: "check", status: "passed", detail: "Проверка результата пройдена." },
    { kind: "verdict", status: "passed", detail: "Проверенный результат готов." },
  ],
});

const summary = normalizeWorkSummary({ metadata: { kolibri_work_summary: encoded } });
assert.equal(summary.schema_version, "kolibri.work-summary.v1");
assert.equal(summary.raw_reasoning_exposed, false);
assert.deepEqual(summary.items.map((item) => item.kind), ["plan", "tool", "source", "check", "verdict"]);

assert.equal(normalizeWorkSummary({ metadata: { kolibri_work_summary: "not-json" } }), null);
assert.equal(normalizeWorkSummary({ metadata: { kolibri_work_summary: JSON.stringify({
  v: 1,
  mode: "summary_only",
  items: [{ kind: "plan", status: "passed", detail: "api_key=sk-never-render-this" }],
}) } }), null);
assert.equal(normalizeWorkSummary({ metadata: { kolibri_work_summary: JSON.stringify({
  v: 1,
  mode: "raw_chain_of_thought",
  items: [{ kind: "plan", status: "passed", detail: "unsafe" }],
}) } }), null);

const vite = await createServer({
  root: fileURLToPath(new URL("..", import.meta.url)),
  server: { middlewareMode: true },
  appType: "custom",
  logLevel: "silent",
});
const { WorkSummary } = await vite.ssrLoadModule("/src/windows/shared/WorkSummary.jsx");
await vite.close();

const markup = renderToStaticMarkup(createElement(WorkSummary, { summary }));
assert.match(markup, /Ход работы/);
assert.match(markup, /Проверено/);
assert.match(markup, /aria-expanded="false"/);
assert.doesNotMatch(markup, /Ответ подготовлен/, "details stay collapsed until the user asks for them");

const readiness = normalizeWorkSummary({ metadata: { kolibri_work_summary: JSON.stringify({
  v: 1,
  mode: "summary_only",
  items: [
    { kind: "plan", status: "incomplete", detail: "Черновик исходных данных подготовлен." },
    { kind: "source", status: "blocked", detail: "Нужны подтверждённые источники цен." },
    { kind: "check", status: "blocked", detail: "Проверка ожидает исходных данных." },
    { kind: "verdict", status: "incomplete", detail: "Денежный итог не рассчитан." },
  ],
}) } });
const readinessMarkup = renderToStaticMarkup(createElement(WorkSummary, { summary: readiness }));
assert.match(readinessMarkup, /Нужны данные/);
assert.doesNotMatch(readinessMarkup, /Проверено/);

const connected = normalizeWorkSummary({ metadata: { kolibri_work_summary: JSON.stringify({
  v: 1,
  mode: "summary_only",
  items: [
    { kind: "tool", status: "available", detail: "Инструментальный контур подключён." },
    { kind: "source", status: "available", detail: "Контур источников подключён." },
  ],
}) } });
const connectedMarkup = renderToStaticMarkup(createElement(WorkSummary, { summary: connected }));
assert.match(connectedMarkup, /Подключено/);

const sourceSummary = normalizeWorkSummary({ metadata: {
  kolibri_work_summary: JSON.stringify({
    v: 1,
    mode: "summary_only",
    items: [{ kind: "source", status: "passed", detail: "Использовано источников: 1." }],
  }),
  kolibri_work_sources: JSON.stringify({
    v: 1,
    sources: [{
      url: "https://supplier.example/catalog",
      domain: "supplier.example",
      price_level_date: "2026-Q2",
      captured_at: "2026-07-11",
    }],
  }),
} });
const sourceMarkup = renderToStaticMarkup(createElement(WorkSummary, { summary: sourceSummary, defaultOpen: true }));
assert.match(sourceMarkup, /href="https:\/\/supplier\.example\/catalog"/);
assert.match(sourceMarkup, /supplier\.example/);
assert.match(sourceMarkup, /2026-Q2/);
assert.match(sourceMarkup, /2026-07-11/);

assert.equal(normalizeWorkSummary({ metadata: {
  kolibri_work_summary: JSON.stringify({
    v: 1,
    mode: "summary_only",
    items: [{ kind: "source", status: "passed", detail: "unsafe" }],
  }),
  kolibri_work_sources: JSON.stringify({
    v: 1,
    sources: [{ url: "https://supplier.example/catalog?token=secret", domain: "supplier.example" }],
  }),
} }), null);

assert.equal(normalizeWorkSummary({ metadata: {
  kolibri_work_summary: JSON.stringify({
    v: 1,
    mode: "summary_only",
    items: [{ kind: "source", status: "passed", detail: "unsafe" }],
  }),
  kolibri_work_sources: JSON.stringify({
    v: 1,
    sources: [{ url: "http://10.99.0.2:9101/internal", domain: "10.99.0.2" }],
  }),
} }), null);

assert.equal(normalizeWorkSummary({ metadata: {
  kolibri_work_summary: JSON.stringify({
    v: 1,
    mode: "summary_only",
    items: [{ kind: "source", status: "passed", detail: "unsafe" }],
  }),
  kolibri_work_sources: JSON.stringify({
    v: 1,
    sources: [{ url: "https://supplier.example/token/sk-secret-value-0123456789", domain: "supplier.example" }],
  }),
} }), null);

const css = readFileSync(new URL("../src/App.css", import.meta.url), "utf8");
const projectWorkspace = readFileSync(new URL("../src/windows/ProjectWorkspace.jsx", import.meta.url), "utf8");
assert.match(css, /\.work-summary-trigger/);
assert.match(css, /@media \(max-width: 760px\)[\s\S]*?\.work-summary-panel\s*\{[\s\S]*?position:\s*fixed;[\s\S]*?bottom:\s*0;/);
assert.match(css, /\.work-summary-scrim\s*\{[\s\S]*?position:\s*fixed;/);
assert.doesNotMatch(projectWorkspace, /Выполняю…/);
assert.match(projectWorkspace, /message\.text \|\| message\.progressText/);

console.log("Kolibri safe work-summary metadata, UI, and mobile sheet contracts passed");

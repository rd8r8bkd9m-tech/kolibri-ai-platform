import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const vite = await createServer({
  root: fileURLToPath(new URL("..", import.meta.url)),
  server: { middlewareMode: true },
  appType: "custom",
  logLevel: "silent",
});
const {
  buildEstimateTitle,
  estimateArtifactDisplayName,
  estimateTitleFromPayload,
} = await vite.ssrLoadModule("/src/estimate/estimateTitle.js");
await vite.close();

assert.equal(buildEstimateTitle({
  objectName: "Одноэтажный дом",
  areaM2: "100.00",
  locality: "Лениногорск",
  region: "Республика Татарстан",
}), "Смета: Одноэтажный дом 100 м² — Лениногорск, Татарстан");

assert.equal(buildEstimateTitle({
  objectName: "Одноэтажный дом 100 м²",
  areaM2: "100",
  region: "Республика Татарстан, Лениногорск",
}), "Смета: Одноэтажный дом 100 м² — Лениногорск, Татарстан");

const readinessTitle = estimateTitleFromPayload({
  readiness: {
    title: "Исходные данные для сметы",
    status: "needs_input",
    known_facts: {
      object_type_label: "Одноэтажный жилой дом",
      gross_area_m2: "100",
      locality: "Лениногорск",
      region: "Республика Татарстан",
    },
  },
});
assert.equal(readinessTitle, "Смета: Одноэтажный жилой дом 100 м² — Лениногорск, Татарстан");
assert.doesNotMatch(readinessTitle, /исходные данные|нужны данные|предварительная/i);

assert.equal(estimateTitleFromPayload({
  task: { result: { estimate: { title: "Лучшая цена!", region: "Республика Татарстан, Лениногорск" } } },
}), "Смета: строительные работы — Лениногорск, Татарстан");

assert.equal(buildEstimateTitle({ objectName: "Смета: Монтаж\nотопления\u0000", region: "Москва" }), "Смета: Монтаж отопления — Москва");
assert.equal(estimateArtifactDisplayName({ deliverable_type: "pdf" }, readinessTitle), `PDF · ${readinessTitle}`);

console.log("Kolibri human-readable estimate title contract passed");

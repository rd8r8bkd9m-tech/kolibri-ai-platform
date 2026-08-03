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

test("reference catalog preserves navigation without inventing source data", async () => {
  const catalog = await readSource(
    "components/kolibri-workspace/reference-catalog.tsx",
  );
  const catalogRoute = await readSource("app/api/v3/pricing/catalog/route.ts");

  for (const category of [
    "Работы",
    "Материалы",
    "Единицы",
    "Индексы и коэффициенты",
    "Контрагенты",
    "Шаблоны",
  ]) {
    assert.match(catalog, new RegExp(`label: "${category}"`));
  }

  for (const fabricatedData of [
    "DEMO_SNAPSHOT",
    "REFERENCE_ROWS",
    "ReferenceRow",
    "getCategoryCount",
    "local_demo_frozen",
    "visibleRows",
    "selectedRow",
    "demo-2026.07",
    "25.07.2026",
    "updatedAt",
    "frozenAt",
    "Показано:",
    "Устройство монолитного фундамента",
    "Демонстрационный поставщик",
  ]) {
    assert.doesNotMatch(
      catalog,
      new RegExp(fabricatedData),
      `unexpected fabricated reference data: ${fabricatedData}`,
    );
  }

  assert.doesNotMatch(catalog, /DEMO-[WMUICT]-\d+/);
  assert.doesNotMatch(catalog, /Демо-набор|Учебная позиция|snapshot\s*:/i);
  assert.match(catalog, /\/api\/v3\/pricing\/catalog\?limit=100&projectId=/);
  assert.match(catalog, /crossProjectEnabled:\s*false/);
  assert.match(catalog, /confidence/);
  assert.match(catalog, /aiPreliminary/);
  assert.match(catalog, /scope:\s*["']personal["']/);
  assert.match(catalog, /crossTenantEnabled:\s*false/);
  assert.match(catalog, /data_status:\s*catalogState/);
  assert.match(catalog, /scope:\s*["']tenant_user_private["']/);
  assert.match(catalog, /Межтенантное агрегирование выключено/);
  assert.match(catalog, /Не удалось загрузить справочник/);
  assert.match(catalog, /Цены появятся после создания и редактирования сметы/);
  assert.match(catalog, /<Input\b/);
  assert.match(catalogRoute, /target\.set\("projectId", projectId\)/);
  assert.match(catalogRoute, /target\.set\("category", category\)/);
  assert.match(catalogRoute, /target\.set\("source", catalogSource\)/);
});

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

test("workspace tools expose honest empty states without seeded calculations or offers", async () => {
  const contextPanel = await readSource(
    "components/kolibri-workspace/context-panel.tsx",
  );

  for (const forbiddenSource of [
    "INITIAL_CALCULATION_ROWS",
    "MARKETPLACE_OFFERS",
    "СтройПоставка",
    "Материалы Про",
    "Бетон B22,5",
    "Арматура А500С",
    "Утеплитель фасадный",
    "useAssistantContext",
    "useAui",
  ]) {
    assert.doesNotMatch(
      contextPanel,
      new RegExp(forbiddenSource),
      `unexpected seeded source: ${forbiddenSource}`,
    );
  }

  assert.doesNotMatch(contextPanel, />В проекте?</);
  assert.match(contextPanel, /Расчёты пока не созданы/);
  assert.match(contextPanel, /Подключения маркетплейсов не настроены/);
  assert.match(contextPanel, /Нет активных подключений/);
});

test("workspace desktop keeps real navigation and no hardcoded recent records", async () => {
  const desktop = await readSource(
    "components/kolibri-workspace/workspace-desktop.tsx",
  );

  for (const hardcodedRecord of [
    "Пояснительная записка.docx",
    "Сводная смета.xlsx",
    "сегодня, 09:42",
    "сегодня, 08:55",
    "Активный проект",
  ]) {
    assert.doesNotMatch(
      desktop,
      new RegExp(hardcodedRecord),
      `unexpected recent record: ${hardcodedRecord}`,
    );
  }

  assert.match(desktop, /Недавних документов нет/);

  for (const callback of [
    "onOpenProjects",
    "onOpenDocuments",
    "onOpenReferences",
    "onOpenBrowser",
  ]) {
    assert.match(
      desktop,
      new RegExp(`onClick=\\{${callback}\\}`),
      `missing real navigation callback: ${callback}`,
    );
  }
});

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  diffEstimateDrafts,
  parseEstimateVersionConflict,
} from "../lib/estimate-version-conflict.ts";

const APP_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

const readSource = (relativePath) =>
  readFile(path.join(APP_ROOT, relativePath), "utf8");

const row = (id, description, quantity = "1", unitPrice = "100.00") => ({
  id,
  description,
  unit: "шт.",
  quantity,
  unitPrice,
});

test("estimate version conflicts are recognized only from the typed 409 contract", () => {
  assert.deepEqual(
    parseEstimateVersionConflict(409, {
      detail: {
        code: "estimate_version_conflict",
        expected_version: 4,
        current_version: 6,
      },
    }),
    { expectedVersion: 4, currentVersion: 6 },
  );
  assert.deepEqual(
    parseEstimateVersionConflict(409, {
      code: "estimate_version_conflict",
      expected_version: 2,
      current_version: 3,
    }),
    { expectedVersion: 2, currentVersion: 3 },
  );
  assert.equal(
    parseEstimateVersionConflict(500, {
      code: "estimate_version_conflict",
      expected_version: 2,
      current_version: 3,
    }),
    null,
  );
  assert.equal(
    parseEstimateVersionConflict(409, {
      detail: { code: "thread_version_conflict" },
    }),
    null,
  );
});

test("the conflict diff separates local, remote, and overlapping draft edits", () => {
  const baseline = {
    title: "Смета",
    rows: [row("row_1", "Штукатурка"), row("row_2", "Грунтовка")],
  };
  const local = {
    title: "Локальная смета",
    rows: [
      row("row_1", "Штукатурка", "2"),
      row("row_2", "Грунтовка"),
      row("row_3", "Локальная позиция"),
    ],
  };
  const remote = {
    title: "Серверная смета",
    rows: [
      row("row_1", "Штукатурка", "3"),
      row("row_2", "Грунтовка глубокого проникновения"),
      row("row_4", "Серверная позиция"),
    ],
  };

  const diff = diffEstimateDrafts(baseline, local, remote);

  assert.ok(diff.localChanges.includes("Название сметы"));
  assert.ok(diff.remoteChanges.includes("Название сметы"));
  assert.ok(diff.conflicts.includes("Название сметы"));
  assert.ok(
    diff.localChanges.some((item) => item.includes("Локальная позиция")),
  );
  assert.ok(
    diff.remoteChanges.some((item) => item.includes("Серверная позиция")),
  );
  assert.ok(
    diff.conflicts.some(
      (item) =>
        item.includes("Штукатурка") &&
        item.includes("изменены одни и те же поля"),
    ),
  );
  assert.ok(
    diff.remoteChanges.some((item) => item.includes("Грунтовка")),
  );
});

test("the estimate editor preserves the draft until an explicit conflict action", async () => {
  const source = await readSource(
    "components/assistant-ui/product-widgets.tsx",
  );

  assert.match(source, /parseEstimateVersionConflict\(/);
  assert.match(source, /setSaveState\(["']conflict["']\)/);
  assert.match(source, /latestSnapshotRef\.current/);
  assert.match(source, /data-slot=["']estimate-version-conflict["']/);
  assert.match(source, /data-slot=["']estimate-conflict-diff["']/);
  assert.match(source, /Локальный черновик не изменён/);
  assert.match(source, /Загрузить версию \{versionConflict\.currentVersion\}/);
  assert.match(source, /Сохранить мой черновик поверх версии/);
  assert.match(
    source,
    /saveState === ["']conflict["'] \|\|[\s\S]{0,60}versionConflict/,
  );
});

test("mobile editor and chat stay mounted while visibility changes", async () => {
  const shell = await readSource(
    "components/kolibri-shell/workspace-shell.tsx",
  );

  assert.match(shell, /const threadSurface\s*=\s*\(/);
  assert.match(shell, /data-slot=["']mobile-thread-preserver["']/);
  assert.match(
    shell,
    /mobile-thread-preserver[\s\S]{0,520}\{threadSurface\}/,
  );
  assert.match(shell, /data-slot=["']mobile-primary-workspace["']/);
  assert.match(shell, /mobilePrimaryCanvasMounted/);
  assert.match(shell, /aria-hidden=\{[\s\S]{0,100}accountSurfaceOpen/);
  assert.match(shell, /\binert=\{/);
  assert.match(shell, /\binvisible pointer-events-none\b/);
  assert.doesNotMatch(
    shell,
    /mobilePrimarySurfaceOpen\s*\?\s*canvasSurface\s*:\s*threadSurface/,
  );
});

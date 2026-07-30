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

test("project files default to an honest empty collection", async () => {
  const [manager, canvas] = await Promise.all([
    readSource(
      "components/kolibri-workspace/workspace-file-manager.tsx",
    ),
    readSource("components/kolibri-workspace/canvas-workspace.tsx"),
  ]);

  assert.match(manager, /\bfiles\s*=\s*\[\]/);
  assert.match(manager, /files\?:\s*readonly\s+WorkspaceFile\[\]/);
  assert.match(manager, /В проекте пока нет файлов/);
  assert.doesNotMatch(manager, /\bDEMO_FILES\b/);
  assert.doesNotMatch(
    manager,
    /Пояснительная записка|Сводная смета|Договор подряда|Фото участка/,
  );

  assert.match(canvas, /\bworkspaceFiles\s*=\s*\[\]/);
  assert.match(canvas, /files=\{workspaceFiles\}/);
});

test("artifact surface does not invent document text or estimate rows", async () => {
  const editor = await readSource(
    "components/kolibri-workspace/workspace-artifact-editor.tsx",
  );

  assert.match(editor, /Содержимое ещё не загружено в рабочую область/);
  assert.doesNotMatch(
    editor,
    /DOCUMENT_COPY|DOCUMENT_DRAFTS|ESTIMATE_DRAFTS|initialRows/,
  );
  assert.doesNotMatch(
    editor,
    /демонстрацион|учебный набор|Подготовительные работы|Земляные работы|Монолитные конструкции/i,
  );
});

test("workspace file contracts use product names, not prototype names", async () => {
  const [manager, canvas, session, barrel] = await Promise.all([
    readSource(
      "components/kolibri-workspace/workspace-file-manager.tsx",
    ),
    readSource("components/kolibri-workspace/canvas-workspace.tsx"),
    readSource("components/kolibri-workspace/canvas-session.ts"),
    readSource("components/kolibri-workspace/index.ts"),
  ]);

  for (const source of [manager, canvas, session, barrel]) {
    assert.doesNotMatch(source, /\bDemoWorkspaceFile(?:Kind)?\b/);
  }

  assert.match(manager, /export type WorkspaceFileKind/);
  assert.match(manager, /export type WorkspaceFile\s*=/);
  assert.match(barrel, /\bWorkspaceFileKind\b/);
  assert.match(barrel, /\bWorkspaceFile\b/);
});

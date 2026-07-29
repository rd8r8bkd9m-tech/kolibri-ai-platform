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

test("the workspace shell does not fabricate projects or project metadata", async () => {
  const [sidebar, shell, header, overview] = await Promise.all([
    readSource("components/kolibri-shell/workspace-sidebar.tsx"),
    readSource("components/kolibri-shell/workspace-shell.tsx"),
    readSource("components/kolibri-shell/workspace-header.tsx"),
    readSource("components/kolibri-workspace/projects-overview.tsx"),
  ]);
  const sources = [sidebar, shell, header, overview].join("\n");

  for (const fabricatedValue of [
    "Жилой дом",
    "Детский сад № 12",
    "Реконструкция цеха",
    "Смета и договоры",
    "Исходные данные",
    "Обследование",
    "Демонстрационные статусы и числа",
  ]) {
    assert.doesNotMatch(sources, new RegExp(fabricatedValue));
  }

  assert.doesNotMatch(sources, /\bDesignDemoProject\b/);
  assert.doesNotMatch(sources, /\bDESIGN_DEMO_PROJECTS\b/);
  assert.doesNotMatch(overview, /\bDEMO_PROJECT_METADATA\b/);
  assert.match(
    sidebar,
    /WORKSPACE_PROJECTS:\s*readonly WorkspaceProject\[\]\s*=\s*\[\]/,
  );
  assert.match(
    shell,
    /useState<WorkspaceProject \| null>\(null\)/,
  );
});

test("an empty account gets honest project and desktop states", async () => {
  const [overview, shell, header] = await Promise.all([
    readSource("components/kolibri-workspace/projects-overview.tsx"),
    readSource("components/kolibri-shell/workspace-shell.tsx"),
    readSource("components/kolibri-shell/workspace-header.tsx"),
  ]);

  assert.match(overview, /Проектов пока нет/);
  assert.match(overview, /после сохранения сервером/);
  assert.match(overview, /disabled=\{projects\.length === 0\}/);
  assert.match(shell, /:\s*["']workspace:files["']/);
  assert.match(shell, /activeProject\?\.(?:id|name)/);
  assert.match(header, /projectName\?\.trim\(\) \|\| null/);
  assert.match(header, /Проект не выбран/);
});

test("project rows open directly and remain distinguishable", async () => {
  const overview = await readSource(
    "components/kolibri-workspace/projects-overview.tsx",
  );

  assert.match(overview, /onClick=\{\(\)\s*=>\s*onOpenProject\(project\)\}/);
  assert.match(overview, /project\.id\.slice\(-8\)/);
  assert.doesNotMatch(overview, /onProjectSelect/);
  assert.doesNotMatch(overview, />\s*Открыть\s*</);
});

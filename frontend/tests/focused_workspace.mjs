import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

import { buildConversationMessages } from "../src/runtime/kolibriApi.js";
import { initialWorkbench, workbenchReducer } from "../src/workbench/reducer.js";
import { initialShellNavigation, shellNavigationReducer } from "../src/shell/shellNavigationModel.js";

// Load application modules through the same resolver used by the product;
// the browser source intentionally uses extensionless local imports.
const vite = await createServer({
  root: fileURLToPath(new URL("..", import.meta.url)),
  server: { middlewareMode: true },
  appType: "custom",
  logLevel: "silent",
});
const { detectIntent } = await vite.ssrLoadModule("/src/app/utils.js");
const {
  buildTaskForIntent,
  estimateCanvas,
  projectWindow,
  taskCanvas,
  upsertCanvas,
} = await vite.ssrLoadModule("/src/shell/projectModel.js");
await vite.close();

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const publicShell = read("../src/shell/PublicShell.jsx");
const projectCommands = read("../src/shell/useProjectCommands.js");
const projectMessaging = read("../src/shell/useProjectMessaging.js");
const projectStore = read("../src/shell/useProjectStore.js");
const executionModeSupport = read("../src/shell/useExecutionModeSupport.js");
const workbenchController = read("../src/shell/useWorkbenchController.js");
const workbench = read("../src/workbench/Workbench.jsx");
const windowFrame = read("../src/workbench/WindowFrame.jsx");
const composer = read("../src/shell/Composer.jsx");
const minimizedWindows = read("../src/shell/MinimizedWindows.jsx");
const toolDock = read("../src/shell/ToolDock.jsx");
const projectWorkspace = read("../src/windows/ProjectWorkspace.jsx");
const projectCanvas = read("../src/windows/ProjectCanvas.jsx");
const estimateWorkspace = read("../src/windows/EstimateWorkspace.jsx");
const projectsWindow = read("../src/windows/ProjectsWindow.jsx");
const pdfViewer = read("../src/windows/PdfViewer.jsx");
const css = read("../src/App.css");

const projectA = {
  id: "project-a",
  title: "Первый проект",
  messages: [],
  artifacts: [],
  canvases: [],
};
const projectB = { ...projectA, id: "project-b", title: "Второй проект" };

// Ordinary conversation stays a conversation. Only an explicit typed intent
// produces an editable canvas, never another chat/window per prompt.
assert.equal(detectIntent("Привет. Ты кто?"), "response");
assert.equal(detectIntent("Расскажи, что такое смета"), "response");
assert.equal(detectIntent("Составь смету"), "estimate");
assert.equal(buildTaskForIntent("response", "Привет"), null);
assert.equal(buildTaskForIntent("document", "Подготовь документ").intent, "document");
assert.deepEqual(buildTaskForIntent("estimate", "Составь смету").requested_artifacts, ["pdf"]);

const secondExchange = buildConversationMessages([
  { id: "u-1", role: "user", text: "Привет" },
  { id: "a-1", role: "assistant", text: "Здравствуйте", status: "completed" },
  { id: "a-running", role: "assistant", text: "Черновик", status: "running" },
  { id: "a-failed", role: "assistant", text: "Ошибка", status: "failed" },
], "Что ты умеешь?");
assert.deepEqual(secondExchange, [
  { role: "user", content: "Привет" },
  { role: "assistant", content: "Здравствуйте" },
  { role: "user", content: "Что ты умеешь?" },
]);
assert.equal(secondExchange.filter((message) => message.content === "Что ты умеешь?").length, 1);

// The primary chat is not represented by an OS window. Explicitly detached
// projects use stable IDs and opening the same project never duplicates it.
assert.deepEqual(initialWorkbench.windows, []);
let desktop = workbenchReducer(initialWorkbench, { type: "OPEN", window: projectWindow(projectA) });
desktop = workbenchReducer(desktop, { type: "OPEN", window: projectWindow(projectA) });
assert.equal(desktop.windows.length, 1);
assert.equal(desktop.windows[0].id, "workspace:project-a");
desktop = workbenchReducer(desktop, { type: "OPEN", window: projectWindow(projectB) });
assert.deepEqual(desktop.windows.map((item) => item.id), ["workspace:project-a", "workspace:project-b"]);

desktop = workbenchReducer(desktop, { type: "MINIMIZE", id: "workspace:project-a" });
assert.equal(desktop.windows.find((item) => item.id === "workspace:project-a").minimized, true);
desktop = workbenchReducer(desktop, { type: "FOCUS", id: "workspace:project-a" });
assert.equal(desktop.windows.find((item) => item.id === "workspace:project-a").minimized, false);
desktop = workbenchReducer(desktop, { type: "MAXIMIZE", id: "workspace:project-a" });
assert.equal(desktop.windows.find((item) => item.id === "workspace:project-a").maximized, true);

const persistedProjects = [projectA, projectB];
desktop = workbenchReducer(desktop, { type: "DEACTIVATE", id: "workspace:project-a" });
assert.equal(desktop.windows.some((item) => item.id === "workspace:project-a"), false);
assert.equal(persistedProjects.some((project) => project.id === "project-a"), true, "closing a window must not delete its project");

// Product regression: pin/collapse navigation, open the composer picker, then
// maximize/restore a result window. These independent state machines must keep
// stable state and never remount the primary project into another chat.
let navigationState = shellNavigationReducer(initialShellNavigation, { type: "PIN_TOGGLE" });
assert.equal(navigationState.pinned, true);
navigationState = shellNavigationReducer(navigationState, { type: "PIN_TOGGLE" });
assert.deepEqual(navigationState, initialShellNavigation);
const composerState = { toolMenuOpen: true };
desktop = workbenchReducer(desktop, { type: "OPEN", window: { id: "artifact:pdf", kind: "pdf", title: "Смета PDF" } });
desktop = workbenchReducer(desktop, { type: "MAXIMIZE", id: "artifact:pdf" });
desktop = workbenchReducer(desktop, { type: "MAXIMIZE", id: "artifact:pdf" });
assert.equal(desktop.windows.find((item) => item.id === "artifact:pdf").maximized, false);
assert.equal(composerState.toolMenuOpen, true);

const estimate = estimateCanvas(projectA.id);
const documentCanvas = taskCanvas({
  id: "reply-1",
  intent: "document",
  title: "Документ",
  status: "completed",
  text: "Готово",
  task: { status: "completed" },
  artifacts: [],
  endpoint: "/v1/responses",
});
const canvases = upsertCanvas(upsertCanvas([], estimate), documentCanvas);
assert.deepEqual(canvases.map((canvas) => canvas.kind), ["estimate", "document"]);
assert.equal(upsertCanvas(canvases, { ...documentCanvas, version: 2 }).length, 2);
const readinessCanvas = taskCanvas({
  id: "reply-readiness",
  intent: "estimate",
  title: "Смета на дом",
  status: "incomplete",
  text: "Денежный итог не рассчитан",
  task: {
    status: "incomplete",
    result: {
      type: "estimate_readiness",
      readiness: {
        title: "Исходные данные для сметы",
        known_facts: { region: "Республика Татарстан" },
      },
    },
  },
  artifacts: [],
  endpoint: "/v1/responses",
});
assert.equal(readinessCanvas.title, "Исходные данные для сметы");
assert.equal(readinessCanvas.readiness.known_facts.region, "Республика Татарстан");
assert.match(readinessCanvas.metadata.provenance, /заблокирован/);

assert.match(publicShell, /const renderPrimary/);
assert.match(publicShell, /renderPrimary=\{renderPrimary\}/);
assert.match(workbench, /className="primary-surface"/);
assert.match(workbench, /<PrimarySurface>\{renderPrimary\(\)\}<\/PrimarySurface>/);
assert.doesNotMatch(projectMessaging, /type:\s*"OPEN"/);
assert.match(projectMessaging, /task \? taskCanvas\(/);
assert.match(projectMessaging, /canvases:\s*canvas \? upsertCanvas/);
assert.match(projectCommands, /const newProject[\s\S]*setActiveProjectId\(project\.id\)/);
assert.doesNotMatch(projectCommands.match(/const newProject[\s\S]*?\}, \[[^\]]*\]\);/)?.[0] || "", /openProject/);
assert.match(projectCommands, /openCanvas\(projectId, canvas\)/);
assert.match(projectCommands, /draftTool:\s*tool,\s*viewMode:\s*"dialog"/);
assert.doesNotMatch(projectCommands, /estimateCanvas|upsertCanvas/);
assert.doesNotMatch(projectStore, /deleteProject|removeProject/);
assert.match(workbenchController, /dispatch\(\{ type: "OPEN", window: projectWindow\(project, maximized\) \}\)/);
assert.match(publicShell, /onOpenHistory=\{shell\.openProject\}/);
assert.match(projectsWindow, /onClick=\{\(\) => onOpen\(item\)\}/);
assert.match(projectWorkspace, /onDetachProject\(project\)/);
assert.match(projectCanvas, /onClick=\{onDetach\}/);
assert.match(pdfViewer, /\/v1\\\/public\\\/estimate-artifacts/);
assert.match(pdfViewer, /<iframe/);
assert.doesNotMatch(pdfViewer, /xlsx/i);
assert.match(estimateWorkspace, /EstimateReadinessWorkspace/);
assert.match(estimateWorkspace, /Денежный итог не рассчитан/);
assert.match(estimateWorkspace, /readinessDraftSavedAt/);
assert.match(estimateWorkspace, /Сохранить черновик/);
assert.match(estimateWorkspace, /Предварительная смета/);
assert.match(estimateWorkspace, /provenanceSummary/);
assert.match(estimateWorkspace, /submitEstimateFeedback/);
assert.match(estimateWorkspace, /FormulaLM/);
assert.match(css, /\.estimate-verification-banner/);
assert.match(css, /\.estimate-line-provenance/);

assert.match(toolDock, /<MinimizedWindows/);
assert.match(minimizedWindows, /<AnimatePresence/);
assert.match(minimizedWindows, /<motion\.button/);
assert.match(windowFrame, /type:\s*"MINIMIZE"/);
assert.match(windowFrame, /type:\s*"DEACTIVATE"/);
assert.match(windowFrame, /\? \{ inset: 0, zIndex:/);
assert.match(publicShell, /shell\.immersive \? "is-immersive"/);
assert.match(css, /\.kolibri-workbench\.is-immersive \.system-bar,[\s\S]*?\.kolibri-workbench\.is-immersive \.tool-dock\s*\{\s*display:\s*none/s);
assert.match(css, /\.kolibri-workbench\.is-immersive \.workbench-body\s*\{[^}]*height:\s*100svh/s);

assert.match(projectWorkspace, /<Composer/);
assert.match(composer, /event\.key === "Enter" && !event\.shiftKey/);
assert.match(composer, /const supported = executionModes\.includes\(mode\.id\)/);
assert.match(composer, /disabled=\{!supported\}/);
assert.match(executionModeSupport, /if \(active\) setExecutionModes\(modes\)/);
assert.match(executionModeSupport, /active = false;\s*controller\.abort\(\)/);
assert.match(css, /\.stage-window\s*\{[^}]*position:\s*absolute/s);
assert.match(css, /\.project-workspace\s*\{/);
assert.match(css, /\.composer-layer\.is-embedded\s*\{[^}]*position:\s*relative/s);
assert.doesNotMatch(css, /linear-gradient|radial-gradient/);

console.log("Kolibri primary chat and multiwindow lifecycle contracts passed");

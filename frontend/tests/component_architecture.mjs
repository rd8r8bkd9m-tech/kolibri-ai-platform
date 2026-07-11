import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const app = read("../src/App.jsx");
const publicShell = read("../src/shell/PublicShell.jsx");
const publicShellLogic = read("../src/shell/usePublicShell.js");
const projectMessaging = read("../src/shell/useProjectMessaging.js");
const projectCommands = read("../src/shell/useProjectCommands.js");
const estimateRuntime = read("../src/shell/useEstimateRuntime.js");
const executionModeSupport = read("../src/shell/useExecutionModeSupport.js");
const projectModel = read("../src/shell/projectModel.js");
const projectStore = read("../src/shell/useProjectStore.js");
const workbenchController = read("../src/shell/useWorkbenchController.js");
const controlShell = read("../src/control/ControlShell.jsx");
const systemBar = read("../src/shell/SystemBar.jsx");
const windowContent = read("../src/windows/WindowContent.jsx");

const componentModules = new Map([
  ["../src/components/ErrorBoundary.jsx", /export class ErrorBoundary/],
  ["../src/shell/Brand.jsx", /export function Brand/],
  ["../src/shell/SystemBar.jsx", /export function SystemBar/],
  ["../src/shell/ToolDock.jsx", /export function ToolDock/],
  ["../src/shell/Composer.jsx", /export function Composer/],
  ["../src/shell/MinimizedWindows.jsx", /export function MinimizedWindows/],
  ["../src/shell/PublicShell.jsx", /export function PublicShell/],
  ["../src/workbench/WindowFrame.jsx", /export function WindowFrame/],
  ["../src/workbench/MobileWindow.jsx", /export function MobileWindow/],
  ["../src/windows/WindowContent.jsx", /export function WindowContent/],
  ["../src/windows/ProjectCanvas.jsx", /export function ProjectCanvas/],
  ["../src/windows/TaskResult.jsx", /export function TaskResult/],
  ["../src/windows/EstimateWorkspace.jsx", /export function EstimateWorkspace/],
  ["../src/windows/ProjectsWindow.jsx", /export function ProjectsWindow/],
  ["../src/windows/FilesWindow.jsx", /export function FilesWindow/],
  ["../src/windows/PdfViewer.jsx", /export function PdfViewer/],
  ["../src/windows/ProjectWorkspace.jsx", /export function ProjectWorkspace/],
  ["../src/windows/shared/StatusBadge.jsx", /export function StatusBadge/],
  ["../src/windows/shared/WorkSummary.jsx", /export function WorkSummary/],
  ["../src/control/ControlShell.jsx", /export function ControlShell/],
]);

assert.ok(app.split("\n").length <= 20, "App.jsx must stay a small route composition module");
assert.match(app, /<ErrorBoundary>/);
assert.match(app, /isControlRoute \? <ControlShell \/> : <PublicShell \/>/);
assert.doesNotMatch(app, /useState|useEffect|useReducer|sendKolibriRequest|loadControlSnapshot|className=/);
assert.ok(publicShell.split("\n").length <= 90, "PublicShell.jsx must remain component composition, not orchestration");
assert.ok(publicShellLogic.split("\n").length <= 90, "usePublicShell must remain hook composition, not a monolith");
assert.ok(projectMessaging.split("\n").length <= 130, "project messaging must remain a bounded runtime hook");
assert.ok(projectCommands.split("\n").length <= 80, "project commands must remain a bounded orchestration hook");
assert.ok(estimateRuntime.split("\n").length <= 90, "estimate execution must remain a bounded runtime hook");
assert.ok(executionModeSupport.split("\n").length <= 40, "execution-mode handshake must remain bounded");
assert.ok(projectStore.split("\n").length <= 80, "project storage must remain a bounded state hook");
assert.ok(workbenchController.split("\n").length <= 130, "window orchestration must remain a bounded controller hook");
assert.doesNotMatch(publicShell, /useState|useEffect|useReducer|sendKolibriRequest|buildDocumentTask/);
assert.match(publicShellLogic, /export function usePublicShell/);
assert.match(publicShellLogic, /useProjectMessaging/);
assert.match(publicShellLogic, /useProjectCommands/);
assert.match(publicShellLogic, /useEstimateRuntime/);
assert.match(publicShellLogic, /useExecutionModeSupport/);
assert.match(publicShellLogic, /useProjectStore/);
assert.match(publicShellLogic, /useWorkbenchController/);

for (const [path, exportPattern] of componentModules) {
  assert.match(read(path), exportPattern, `${path} must keep its component boundary`);
}

for (const component of ["ToolDock", "WindowContent"]) {
  assert.match(publicShell, new RegExp(`<${component}(?:\\s|>)`));
  assert.doesNotMatch(publicShell, new RegExp(`function\\s+${component}\\s*\\(`));
}

for (const component of ["ProjectWorkspace", "ProjectCanvas", "EstimateWorkspace", "ProjectsWindow", "FilesWindow", "PdfViewer", "TaskResult"]) {
  assert.match(windowContent, new RegExp(`<${component}(?:\\s|>)`));
}

assert.match(projectModel, /buildDocumentTask/);
assert.match(projectModel, /buildSiteTask/);
assert.match(projectModel, /buildAppTask/);
assert.match(estimateRuntime, /buildDeterministicEstimateTask/);
assert.match(projectMessaging, /sendKolibriRequest/);
assert.doesNotMatch(projectMessaging, /type:\s*"OPEN"/);
assert.doesNotMatch(`${projectModel}\n${projectMessaging}`, /requested_artifacts:\s*\[[^\]]+\][\s\S]*sendKolibriRequest/s);
assert.match(systemBar, /<Brand \/>/);
assert.match(publicShell, /<SystemBar/);
assert.match(controlShell, /<SystemBar/);
assert.doesNotMatch(publicShell, /<HistoryDrawer/);
assert.match(read("../src/windows/ProjectWorkspace.jsx"), /<Composer/);

console.log("Kolibri component architecture contracts passed");

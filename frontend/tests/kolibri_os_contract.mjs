import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

import { API_ENDPOINTS, normalizeCapabilities, normalizeModels, normalizeNodes, normalizeTasks } from "../src/runtime/kolibriApi.js";
import { FALLBACK_RENDERER, RENDERER_REGISTRY, rendererForArtifact } from "../src/runtime/rendererRegistry.js";

assert.equal(API_ENDPOINTS.response, "/v1/responses");
assert.equal(API_ENDPOINTS.publicSession, "/v1/public/session");
assert.equal(API_ENDPOINTS.publicProjects, "/v1/projects");
assert.equal(API_ENDPOINTS.browserSessions, "/v1/browser-sessions");
assert.equal(API_ENDPOINTS.automationValidate, "/v1/automations/validate");
assert.ok(API_ENDPOINTS.nodes.includes("/v1/fleet/nodes"));
assert.equal(API_ENDPOINTS.publicCapabilities[0], "/v1/capabilities");
assert.equal(API_ENDPOINTS.capabilities[0], "/v1/runtime/product-capabilities");

const tasks = normalizeTasks({ tasks: [{ task_id: "t-1", state: "running", envelope: { objective: "Build app" } }] });
assert.equal(tasks[0].title, "Build app");
assert.equal(tasks[0].state, "running");
assert.equal(normalizeNodes({ data: { nodes: [{ node_id: "n-1" }] } })[0].node_id, "n-1");
assert.equal(normalizeModels({ data: { object: "list", data: [{ id: "model-1" }] } })[0].id, "model-1");
assert.equal(normalizeCapabilities({ object: "list", data: [{ id: "tool-1" }] })[0].id, "tool-1");

const requiredRendererKinds = ["website", "pdf", "spreadsheet", "document", "image", "audio", "video", "code", "terminal", "plan", "estimate", "automation"];
assert.deepEqual(RENDERER_REGISTRY.map((renderer) => renderer.kind), requiredRendererKinds);
assert.equal(rendererForArtifact({ status: "materialized", media_type: "application/pdf" }).id, "pdf");
assert.equal(rendererForArtifact({ status: "materialized", kind: "unknown" }).id, FALLBACK_RENDERER.id);
assert.equal(rendererForArtifact({ status: "pending", media_type: "application/pdf" }), null);
assert.ok(RENDERER_REGISTRY.every((renderer) => renderer.sandbox && renderer.modes.length > 0));

const appSource = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
const publicShellSource = readFileSync(new URL("../src/shell/PublicShell.jsx", import.meta.url), "utf8");
const publicShellLogicSource = readFileSync(new URL("../src/shell/usePublicShell.js", import.meta.url), "utf8");
const projectMessagingSource = readFileSync(new URL("../src/shell/useProjectMessaging.js", import.meta.url), "utf8");
const projectMessagingModelSource = readFileSync(new URL("../src/shell/projectMessagingModel.js", import.meta.url), "utf8");
const projectModelSource = readFileSync(new URL("../src/shell/projectModel.js", import.meta.url), "utf8");
const controlShellSource = readFileSync(new URL("../src/control/ControlShell.jsx", import.meta.url), "utf8");
const controlViewModelSource = readFileSync(new URL("../src/control/controlViewModel.js", import.meta.url), "utf8");
const composerSource = readFileSync(new URL("../src/shell/Composer.jsx", import.meta.url), "utf8");
const shellComposerSource = readFileSync(new URL("../src/shell/ShellComposer.jsx", import.meta.url), "utf8");
const shellWorkbenchSource = readFileSync(new URL("../src/shell/ShellWorkbench.jsx", import.meta.url), "utf8");
const workbenchSource = readFileSync(new URL("../src/workbench/Workbench.jsx", import.meta.url), "utf8");
const windowFrameSource = readFileSync(new URL("../src/workbench/WindowFrame.jsx", import.meta.url), "utf8");
const stageLayoutSource = readFileSync(new URL("../src/workbench/useStageLayout.js", import.meta.url), "utf8");
const mobileWindowSource = readFileSync(new URL("../src/workbench/MobileWindow.jsx", import.meta.url), "utf8");
const taskResultSource = readFileSync(new URL("../src/windows/TaskResult.jsx", import.meta.url), "utf8");
const windowContentSource = readFileSync(new URL("../src/windows/WindowContent.jsx", import.meta.url), "utf8");
const projectWorkspaceSource = readFileSync(new URL("../src/windows/ProjectWorkspace.jsx", import.meta.url), "utf8");
const shellSource = [
  appSource,
  publicShellSource,
  publicShellLogicSource,
  projectMessagingSource,
  projectMessagingModelSource,
  projectModelSource,
  controlShellSource,
  composerSource,
  shellComposerSource,
  shellWorkbenchSource,
  workbenchSource,
  windowFrameSource,
  mobileWindowSource,
  taskResultSource,
  windowContentSource,
  projectWorkspaceSource,
].join("\n");
const cssSource = readFileSync(new URL("../src/App.css", import.meta.url), "utf8");
const apiSource = readFileSync(new URL("../src/runtime/kolibriApi.js", import.meta.url), "utf8");
const constantsSource = readFileSync(new URL("../src/app/constants.js", import.meta.url), "utf8");
const toolAvailabilitySource = readFileSync(new URL("../src/app/toolAvailability.js", import.meta.url), "utf8");
const mainSource = readFileSync(new URL("../src/main.jsx", import.meta.url), "utf8");
const retiredServiceWorkerSource = readFileSync(new URL("../public/sw.js", import.meta.url), "utf8");
const viteSource = readFileSync(new URL("../vite.config.js", import.meta.url), "utf8");
const mascotSource = readFileSync(new URL("../src/components/KolibriBird.jsx", import.meta.url), "utf8");
const mascotBytes = readFileSync(new URL("../public/kolibri-bird.png", import.meta.url));
const forbiddenEnglishFallback = new RegExp(["Kolibri could not produce", "a verified response"].join(" "), "i");
const unimplementedClaim = new RegExp(["coming", "soon"].join(" "), "i");

assert.equal(createHash("sha256").update(mascotBytes).digest("hex"), "6f30357f75c963e5e4d85b464b10eadb2545d2a6b40aced54861571c4322c3d7");
assert.match(mascotSource, /src="\/kolibri-bird\.png"/);
assert.doesNotMatch(mascotSource, /<svg|linearGradient|radialGradient|<path/);
assert.doesNotMatch(shellSource, /selectedProvider|Выберите модель|provider-badge/);
assert.doesNotMatch(apiSource, /192\.168\.|10\.99\./);
assert.match(apiSource, /model:\s*"kolibri"/);
assert.match(apiSource, /const idempotencyKey = `shell:/);
assert.match(apiSource, /idempotency_key:\s*idempotencyKey/);
assert.match(apiSource, /response\.output_text\.delta/);
assert.match(apiSource, /response\.completed/);
assert.doesNotMatch(apiSource, forbiddenEnglishFallback);
assert.doesNotMatch(apiSource, unimplementedClaim);
assert.doesNotMatch(apiSource, /response:\s*\["\/api\/chat"/);
assert.match(mainSource, /navigator\.serviceWorker\.getRegistrations\(\)/);
assert.match(mainSource, /registration\.unregister\(\)/);
assert.match(mainSource, /caches\.delete\(key\)/);
assert.match(retiredServiceWorkerSource, /self\.registration\.unregister\(\)/);
assert.match(retiredServiceWorkerSource, /self\.caches\.delete\(key\)/);
assert.doesNotMatch(retiredServiceWorkerSource, /addEventListener\(["']fetch["']/);
const responsesTransport = apiSource.match(/async function requestResponsesStream[\s\S]*?return consumeResponsesSse\(response, onWorkSummary, onTextDelta\);\n}/)?.[0] || "";
assert.ok(responsesTransport);
assert.doesNotMatch(responsesTransport, /Authorization|Bearer/);
assert.match(viteSource, /resolveApiProxy/);
assert.match(viteSource, /resolveCanonicalApiProxy/);
assert.match(viteSource, /readFileSync\(new URL\('\.\/CNAME'/);
assert.match(viteSource, /createProxyRoutes/);
assert.doesNotMatch(viteSource, /127\.0\.0\.1:8000/);
assert.doesNotMatch(`${shellSource}\n${cssSource}`, /project-rail|rail-overlay|mobile-rail/);
assert.doesNotMatch(cssSource, /(^|[,{]\s*)\.chat(?:[\s.{:#>])/m);
assert.doesNotMatch(shellSource, /className=["'][^"']*\bchat\b/);
assert.doesNotMatch(appSource, /useReducer\(|useState\(|sendKolibriRequest/);
assert.match(publicShellSource, /<ShellWorkbench/);
assert.match(publicShellSource, /<ShellComposer/);
assert.match(shellWorkbenchSource, /<Workbench/);
assert.match(shellComposerSource, /<Composer/);
assert.doesNotMatch(publicShellSource, /<HistoryDrawer/);
assert.doesNotMatch(projectWorkspaceSource, /<Composer/);
assert.match(windowContentSource, /<ProjectWorkspace/);
assert.match(publicShellLogicSource, /useProjectMessaging/);
assert.doesNotMatch(projectMessagingSource, /type:\s*"OPEN"/);
assert.match(projectMessagingSource, /task \? taskCanvas\(/);
assert.match(projectMessagingModelSource, /\[\.\.\.current\.messages, turn\.userMessage, turn\.reply\]/);
assert.match(projectMessagingModelSource, /retrying \? requestHistoryForRetry/);
assert.match(projectModelSource, /id: `workspace:\$\{project\.id\}`/);
assert.match(workbenchSource, /className="primary-surface"/);
assert.match(windowFrameSource, /export function WindowFrame/);
assert.match(windowFrameSource, /if \(!frame\) return;/, "detached window gestures must fail closed");
assert.match(stageLayoutSource, /const stage = ref\.current;/, "stage measurement must capture a stable element");
assert.match(stageLayoutSource, /if \(!stage\.isConnected\) return;/, "queued ResizeObserver callbacks must ignore detached stages");
assert.match(mobileWindowSource, /export function MobileWindow/);
assert.match(cssSource, /\.stage-window|\.stage-canvas/);
assert.match(taskResultSource, /Текстовый результат не получен/);
assert.match(controlShellSource, /Фактическое состояние/);
assert.match(controlShellSource, /data-state=\{metric\.state\}/);
assert.match(controlViewModelSource, /Данные Home сейчас недоступны; нулевые значения не подставляются/);
assert.doesNotMatch(projectMessagingSource, /error\?\.message|"Готово\."/);
const publicToolsSource = constantsSource.match(/export const TOOLS[\s\S]*?\n\]\);/)?.[0] || "";
assert.ok(publicToolsSource);
assert.match(publicToolsSource, /id:\s*"image"/, "verified image generation needs a renderer-backed catalog entry");
assert.match(toolAvailabilitySource, /item\?\.status === "available"/, "catalog entries stay hidden until the server promotes them");

console.log("Kolibri OS protocol, Vista workbench, brand, and truthful-data contracts passed");

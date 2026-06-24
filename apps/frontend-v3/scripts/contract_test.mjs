import fs from "node:fs"
import path from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")

function read(file) {
  return fs.readFileSync(path.join(root, file), "utf8")
}

function assert(condition, message) {
  if (!condition) {
    console.error(`contract failed: ${message}`)
    process.exit(1)
  }
}

const contracts = read("src/contracts.js")
const runtime = read("src/canvasRuntime.js")
const app = read("src/App.jsx")
const stage = read("src/CanvasStage.jsx")
const css = read("src/styles.css")
const main = read("src/main.jsx")
const html = read("index.html")
const manifest = read("public/manifest.webmanifest")
const serviceWorker = read("public/sw.js")
assert(!fs.existsSync(path.join(root, "src/estimateEngine.js")), "frontend-v3 shell must not ship hardcoded estimate engine")
assert(!fs.existsSync(path.join(root, "src/CanvasRenderer.jsx")), "frontend-v3 screen must not use DOM canvas renderer")
assert(!html.includes("<div id=\"root\""), "HTML root must not add a root div")
assert(html.includes("<section id=\"root\""), "HTML root should be a semantic mount point")
assert(html.includes("manifest.webmanifest"), "PWA manifest must be linked")
assert(html.includes("apple-mobile-web-app"), "mobile PWA meta tags must exist")
assert(main.includes("serviceWorker") && main.includes("/sw.js"), "frontend-v3 must register service worker in production")
assert(manifest.includes("\"display\": \"standalone\""), "PWA manifest must be installable standalone")
assert(manifest.includes("\"start_url\": \"/\""), "PWA manifest must start at SPA root")
assert(serviceWorker.includes("backend_offline"), "service worker must return structured backend offline API errors")
assert(serviceWorker.includes("url.pathname.startsWith(\"/api/\")"), "service worker must handle API separately")
assert(serviceWorker.includes("url.pathname.startsWith(\"/v1/\")"), "service worker must handle factory/backend v1 API separately")
assert(!serviceWorker.split("async function apiFetch")[1].split("async function networkFirstShell")[0].includes("cache.put(request"), "service worker must not cache API responses")

assert(contracts.includes("BLOCK_REGISTRY"), "BLOCK_REGISTRY must exist")
assert(contracts.includes("COMPONENT_REGISTRY"), "COMPONENT_REGISTRY must exist")
assert(contracts.includes("validateCanvasManifest"), "CanvasManifest validator must exist")
assert(contracts.includes("validateCanvasBlock"), "CanvasBlock validator must exist")
assert(contracts.includes("safe") && contracts.includes("review") && contracts.includes("paid") && contracts.includes("destructive"), "risk levels must be represented")

assert(runtime.includes("/api/ai/canvas"), "runtime must call AI canvas endpoint")
assert(runtime.includes("/api/ai/canvas/action"), "runtime must call AI canvas action endpoint")
assert(runtime.includes("/api/status/bird"), "runtime must load backend bird status endpoint")
assert(runtime.includes("/v1/factory/canvas"), "runtime must be able to load backend-generated CanvasManifest screens")
assert(runtime.includes("api_canvas"), "runtime must support registry-declared API canvas actions")
assert(runtime.includes("safeLocalPath"), "runtime must restrict DynamicAction runtime paths")
assert(runtime.includes("CANVAS_RUNTIME_PATHS"), "runtime must restrict DynamicAction API calls to canvas endpoints")
assert(runtime.includes("normalizeBirdStatus"), "runtime must normalize backend bird status contract")
assert(runtime.includes("return path"), "runtime must use relative /api endpoint when no explicit backend is configured")
assert(runtime.includes("validateCanvasManifest"), "runtime must validate model output")
assert(runtime.includes("model_contract_failed"), "runtime must surface invalid CanvasManifest as a canvas error")
assert(runtime.includes("canvasTurnPayload"), "runtime must send typed canvas payloads")
assert(runtime.includes("user_text") && runtime.includes("canvas_manifest"), "runtime must send user text and current CanvasManifest")
assert(runtime.includes("apiErrorResult"), "runtime must preserve structured API errors")
assert(runtime.includes("payment_required"), "runtime must distinguish payment-required errors")
assert(runtime.includes("confirmation_required"), "runtime must distinguish confirmation-required errors")
assert(!runtime.includes("systemPrompts"), "runtime must not import frontend-owned system prompts")
assert(!runtime.includes("buildModelPrompt"), "runtime must not assemble model prompts in frontend")
assert(!runtime.includes("devFallbackManifest"), "runtime must not generate fallback UI")
assert(!runtime.includes("createDynamicAction"), "runtime must not generate actions in frontend")
assert(!runtime.includes("MARKET_ADAPTERS"), "runtime must not hardcode market/domain data")
assert(!runtime.includes("AI-runtime"), "runtime must not show local AI-runtime copy in product UI")
assert(!runtime.includes("Готово."), "runtime must not synthesize assistant completion text")
assert(!runtime.includes("Kimi") && !runtime.includes("kimi") && !runtime.includes("Кими"), "runtime must not expose provider name in product UI")

assert(app.includes("CanvasStage"), "App must render through the real canvas stage")
assert(app.includes("<CanvasStage"), "App must mount one canvas stage")
assert(app.match(/<CanvasStage/g)?.length === 1, "App must mount exactly one canvas stage")
assert(!app.includes("EstimateWorkspace"), "App must not hardcode estimate workspace")
assert(!app.includes("LiveCanvas"), "App must not use a domain-specific canvas")
assert(!app.includes("createInitialEstimate"), "App must not create domain estimate UI directly")
assert(!app.includes("welcome"), "App must not hardcode greeting")
assert(!app.includes("marketKey"), "App must not hardcode market controls")
assert(!app.includes("qaBootedRef"), "App must not auto-submit QA prompts")
assert(!app.includes("runtime offline"), "App must not show local runtime status copy")
assert(!app.includes("messages.map"), "App must not render a chat timeline outside CanvasManifest")
assert(!app.includes("bubble"), "App must not render hardcoded chat bubbles")
assert(!app.includes("message-layer"), "App must not keep a separate message layer")
assert(!app.includes("<div"), "App shell must not use div wrappers for the canvas screen")
assert(!app.includes("<aside"), "App shell must not render DOM side panels")
assert(!app.includes("<nav"), "App shell must not render DOM action menus")
assert(!app.includes("window.confirm"), "approval must be rendered as canvas state, not browser confirm")
assert(!app.includes("Kimi") && !app.includes("kimi") && !app.includes("Кими"), "App must not expose provider name in product UI")
assert(app.includes("screen-canvas"), "App screen must be the canvas")
assert(!app.includes("canvas-viewport"), "App must not use a DOM viewport pretending to be canvas")

assert(stage.includes("<canvas"), "CanvasStage must use an actual canvas element")
assert(stage.includes("getContext(\"2d\")"), "CanvasStage must paint through 2D canvas")
assert(stage.includes("paintManifest"), "CanvasStage must paint CanvasManifest content")
assert(stage.includes("paintBirdStatus"), "CanvasStage must paint quiet backend bird status")
assert(stage.includes("bird_only"), "CanvasStage must allow backend manifest to keep the initial bird-only canvas")
assert(stage.includes("paintRuntimeErrors"), "CanvasStage must paint runtime/API errors on the canvas")
assert(stage.includes("paintApprovalPanel"), "CanvasStage must paint approval state on the canvas")
assert(stage.includes("paintTurnLog"), "CanvasStage must paint user questions inside the canvas")
assert(stage.includes("paintRuntimeProgress"), "CanvasStage must paint public runtime progress inside the canvas")
assert(stage.includes("paintPremiumAurora"), "CanvasStage must paint a premium non-blank canvas background")
assert(stage.includes("paintMaterialGrid"), "CanvasStage must add canvas-native material depth")
assert(stage.includes("shouldPaintBirdStatus"), "CanvasStage must keep idle canvas free from control-plane status panels")
assert(!stage.includes("paintGlassHorizon"), "CanvasStage must not paint a visible horizon stripe artifact")
assert(!stage.includes("paintGlow"), "CanvasStage must not depend on dark radial glow placeholders")
assert(stage.includes("data-approval-mode"), "CanvasStage must expose approval mode for QA")
assert(stage.includes("data-turns-count"), "CanvasStage must expose visible user question count for QA")
assert(stage.includes("data-progress-stage"), "CanvasStage must expose public progress stage for QA")
assert(stage.includes("data-manifest-scroll"), "CanvasStage must expose manifest scroll state for QA")
assert(stage.includes("data-manifest-scroll-max"), "CanvasStage must expose manifest scroll capacity for QA")
assert(stage.includes("onWheel={handleWheel}"), "CanvasStage must support wheel scrolling for long manifests")
assert(stage.includes("onKeyDown={handleKeyDown}"), "CanvasStage must support keyboard scrolling for long manifests")
assert(stage.includes("sr-only-action"), "CanvasStage must expose canvas actions to assistive tech without visible DOM menus")
assert(stage.includes("estimateManifestScrollMax"), "CanvasStage must compute internal canvas scroll limits")
assert(stage.includes("canvas,") && stage.includes("canvas?.errors"), "CanvasStage must pass canvas state into paint for runtime errors")
assert(stage.includes("data-bird-state"), "CanvasStage must expose QA-readable bird state on the canvas element")
assert(stage.includes("data-canvas-title"), "CanvasStage must expose QA-readable canvas title on the canvas element")
assert(!stage.includes("dangerouslySetInnerHTML"), "CanvasStage must not execute arbitrary UI code")
assert(!stage.includes("Kimi") && !stage.includes("kimi") && !stage.includes("Кими"), "CanvasStage must not expose provider name in product UI")
assert(css.includes("100dvh"), "mobile canvas shell must use dynamic viewport height")
assert(css.includes("focus-within"), "composer must have a premium focus state")
assert(css.includes("env(safe-area-inset-bottom)"), "mobile composer must respect safe area")
assert(css.includes(".sr-only-action"), "CSS must hide accessible action controls visually")

for (const [file, source] of Object.entries({ runtime, app, stage })) {
  assert(!/dangerouslySetInnerHTML\s*=|eval\s*\(|new\s+Function\s*\(/i.test(source), `${file} must not execute arbitrary UI code`)
  assert(!/EstimateWorkspace|createInitialEstimate|marketKey|ФСНБ|ФГИС|Минстро|смет/i.test(source), `${file} must not contain domain-specific editor or estimate hardcode`)
}

const {
  dispatchCanvasAction,
  loadBirdStatus,
  loadCanvasScreen,
  normalizeModelResponse,
  requestCanvasTurn,
} = await import(pathToFileURL(path.join(root, "src/canvasRuntime.js")).href)
const { visibleActions } = await import(pathToFileURL(path.join(root, "src/contracts.js")).href)
const { resolveCanvasTheme } = await import(pathToFileURL(path.join(root, "src/canvasTheme.js")).href)
const validManifest = {
  id: "shell",
  title: "Shell",
  type: "custom",
  blocks: [],
  actions: [],
}
const validResult = normalizeModelResponse({ canvas_manifest: validManifest }, {})
assert(validResult.canvas?.manifest?.id === "shell", "runtime must accept backend CanvasManifest payloads")

const innerManifest = {
  ...validManifest,
  id: "inner-shell",
  title: "Inner Shell",
  blocks: [{ id: "inner-text", type: "text", title: "Answer", content: { text: "Visible inner answer" } }],
  actions: [{ component: "button", intent: "ui.next", label: "Next" }],
}
const nestedInText = normalizeModelResponse({
  assistant_text: JSON.stringify({
    assistant_text: "Inner answer ready",
    canvas_manifest: innerManifest,
    parser_state: { stage: "inner" },
    domain_operations: [],
    guardrails: [],
    errors: [],
  }),
  canvas_manifest: {
    ...validManifest,
    id: "outer-shell",
    title: "Outer Shell",
    blocks: [],
  },
}, {})
assert(nestedInText.canvas?.manifest?.id === "inner-shell", "runtime must unwrap CanvasManifest nested in assistant text")
assert(nestedInText.assistantText === "Inner answer ready", "runtime must keep unwrapped assistant text")

const nestedInBlock = normalizeModelResponse({
  assistant_text: "Outer answer",
  canvas_manifest: {
    ...validManifest,
    id: "outer-block-shell",
    blocks: [
      {
        id: "serialized-block",
        type: "text",
        title: "Serialized",
        content: {
          text: `\`\`\`json\n${JSON.stringify({ assistant_text: "Block answer", canvas_manifest: innerManifest })}\n\`\`\``,
        },
      },
    ],
  },
}, {})
assert(nestedInBlock.canvas?.manifest?.id === "inner-shell", "runtime must unwrap CanvasManifest nested in a canvas text block")
assert(nestedInBlock.canvas?.manifest?.actions?.[0]?.risk === "safe", "runtime must repair incomplete model actions before validation")

const menuManifest = {
  ...validManifest,
  actions: [
    userAction("a1", "Импорт", "ui.import"),
    userAction("a2", "Пересчитать", "ui.recalculate"),
    userAction("a3", "factory.view.tasks", "factory.view.tasks"),
    userAction("a4", "JSON schema artifact", "debug.schema"),
    userAction("a5", "Очень длинное действие которое ломает мобильное меню", "ui.long"),
    userAction("a6", "PDF", "ui.pdf"),
    userAction("a7", "Документы", "ui.documents"),
    userAction("a8", "Еще", "ui.more"),
  ],
}
const menuActions = visibleActions(menuManifest, { maxActions: 4 })
assert(menuActions.length === 4, "visibleActions must limit ordinary plus menu actions")
assert(menuActions.map(action => action.label).join("|") === "Импорт|Пересчитать|PDF|Документы", "visibleActions must filter technical menu artifacts")
assert(visibleActions(menuManifest, { opsMode: true, maxActions: 8 }).some(action => action.intent === "factory.view.tasks"), "opsMode must keep factory actions available for agents")

assert(resolveCanvasTheme({ now: new Date("2026-06-24T12:00:00") }).name === "day", "canvas theme must use day by time")
assert(resolveCanvasTheme({ now: new Date("2026-06-24T23:00:00") }).name === "night", "canvas theme must use night by time")
assert(resolveCanvasTheme({ now: new Date("2026-06-24T12:00:00"), text: "сделай темную тему" }).name === "night", "canvas theme must react to user theme request")
assert(resolveCanvasTheme({ manifestTheme: { name: "dusk", backgroundStops: ["#ffffff", "#abcdef"] } }).backgroundStops[1] === "#abcdef", "canvas theme must accept safe manifest theme stops")

const invalidResult = normalizeModelResponse({ canvas_manifest: { id: "broken" } }, { canvas: null })
assert(invalidResult.canvas?.errors?.[0]?.code === "model_contract_failed", "runtime must place invalid CanvasManifest errors in canvas state")

const errorResult = normalizeModelResponse({ errors: [{ code: "validation_failed", message: "bad action", status: 422 }] }, { canvas: null })
assert(errorResult.canvas?.errors?.[0]?.message === "bad action", "runtime must preserve model/API errors in canvas state")

const fetchCalls = []
const originalFetch = globalThis.fetch
globalThis.fetch = async (url, options = {}) => {
  fetchCalls.push({ url, options })
  if (url === "/api/status/bird") {
    return jsonResponse({
      product: "Колибри",
      state: "working",
      label: "Работаю",
      summary: "В работе 3 · очередь 12 · агенты 50",
      metrics: {
        queued_tasks: 12,
        running_tasks: 3,
        active_agents: 50,
        total_agents: 1000,
        quarantined_nodes: 0,
        dead_letter_tasks: 0,
        failed_tasks: 0,
        active_leases: 3,
        global_max_inflight: 1000,
        approval_required: false,
      },
      menu: [{ id: "tasks", label: "Задачи" }],
    })
  }
  if (String(url).startsWith("/v1/factory/canvas")) {
    return jsonResponse({ canvas_manifest: validManifest })
  }
  if (url === "/api/ai/canvas") {
    const body = JSON.parse(options.body || "{}")
    assert(options.method === "POST", "AI canvas turn must use POST")
    assert(body.user_text === "hello canvas", "AI canvas turn must send user text")
    assert(body.canvas_manifest?.id === "shell", "AI canvas turn must send current CanvasManifest")
    assert(!Object.hasOwn(body, "prompt"), "AI canvas turn must not send frontend-built model prompt")
    return jsonResponse({ canvas_manifest: validManifest })
  }
  throw new Error(`Unexpected fetch URL: ${url}`)
}

const birdStatus = await loadBirdStatus()
assert(birdStatus.state === "working", "loadBirdStatus must preserve backend bird state")
assert(birdStatus.metrics.queued_tasks === 12, "loadBirdStatus must preserve queue metric")

const screenResult = await loadCanvasScreen("shell")
assert(screenResult.canvas?.manifest?.id === "shell", "loadCanvasScreen must load /v1/factory/canvas manifest")

const turnResult = await requestCanvasTurn({
  userText: "hello canvas",
  profile: { id: "contract-profile" },
  canvas: screenResult.canvas,
})
assert(turnResult.canvas?.manifest?.id === "shell", "requestCanvasTurn must accept /api/ai/canvas manifest")
assert(fetchCalls.some(call => call.url === "/v1/factory/canvas?screen=shell"), "runtime must fetch /v1/factory/canvas screen")
assert(fetchCalls.some(call => call.url === "/api/ai/canvas"), "runtime must fetch /api/ai/canvas turns")
assert(fetchCalls.some(call => call.url === "/api/status/bird"), "runtime must fetch backend bird status")

const rejectedAction = await dispatchCanvasAction({
  action: {
    payload: {
      runtime: {
        type: "api_canvas",
        path: "/api/private",
      },
    },
  },
  profile: {},
  canvas: screenResult.canvas,
})
assert(rejectedAction.canvas?.errors?.[0]?.code === "validation_failed", "api_canvas actions must reject non-canvas API paths")
globalThis.fetch = originalFetch

console.log("frontend-v3 contract tests passed")

function jsonResponse(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    async json() {
      return payload
    },
  }
}

function userAction(id, label, intent, extra = {}) {
  return {
    id,
    label,
    icon: "spark",
    intent,
    component: "button",
    payloadSchema: {},
    payload: {},
    risk: "safe",
    requiresConfirmation: false,
    ...extra,
  }
}

import { validateCanvasManifest } from "./contracts.js"

const CANVAS_RUNTIME_PATHS = new Set([
  "/api/ai/canvas",
  "/api/ai/canvas/action",
])

export async function loadBirdStatus(signal) {
  try {
    const response = await fetch(aiEndpoint("/api/status/bird"), { signal })
    if (!response.ok) return offlineBirdStatus(response.statusText || "Bird status unavailable")
    return normalizeBirdStatus(await response.json())
  } catch (error) {
    return offlineBirdStatus(error?.name === "AbortError" ? "Запрос остановлен." : "Backend недоступен.")
  }
}

export async function loadCanvasScreen(screen = "shell", signal) {
  const path = `/v1/factory/canvas?screen=${encodeURIComponent(screen)}`
  return requestApiCanvas(path, { method: "GET", signal })
}

export async function requestCanvasTurn({ userText, profile, canvas, signal }) {
  const endpoint = aiEndpoint("/api/ai/canvas")
  if (!endpoint) return missingRuntimeResult(canvas)

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(canvasTurnPayload({ userText, profile, canvas })),
      signal,
    })
    if (!response.ok) return apiErrorResult(canvas, response, await readErrorPayload(response))
    return normalizeModelResponse(await response.json(), { userText, canvas })
  } catch (error) {
    return runtimeErrorResult(canvas, error)
  }
}

export async function dispatchCanvasAction({ action, profile, canvas, signal }) {
  const runtime = action?.payload?.runtime
  if (runtime?.type === "api_canvas") {
    return requestApiCanvas(runtime.path, {
      method: runtime.method || "GET",
      signal,
      canvas,
      body: runtime.body,
    })
  }

  const endpoint = aiEndpoint("/api/ai/canvas/action")
  if (!endpoint) return missingRuntimeResult(canvas)

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action,
        profile,
        canvas_manifest: canvas?.manifest || null,
      }),
      signal,
    })
    if (!response.ok) return apiErrorResult(canvas, response, await readErrorPayload(response))
    return normalizeModelResponse(await response.json(), { userText: action.label, canvas })
  } catch (error) {
    return runtimeErrorResult(canvas, error)
  }
}

async function requestApiCanvas(path, { method = "GET", signal, canvas = null, body = null } = {}) {
  let endpoint
  try {
    endpoint = aiEndpoint(safeLocalPath(path))
  } catch (error) {
    return validationErrorResult(canvas, error)
  }

  try {
    const response = await fetch(endpoint, {
      method: safeMethod(method),
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal,
    })
    if (!response.ok) return apiErrorResult(canvas, response, await readErrorPayload(response))
    return normalizeModelResponse(await response.json(), { canvas })
  } catch (error) {
    return runtimeErrorResult(canvas, error)
  }
}

export function normalizeModelResponse(payload, context = {}) {
  const normalizedPayload = unwrapNestedCanvasPayload(payload)
  const rawManifest = normalizedPayload?.canvas_manifest || normalizedPayload?.manifest
  const payloadErrors = normalizePayloadErrors(normalizedPayload?.errors)
  const assistantText = String(normalizedPayload?.assistant_text || normalizedPayload?.message || "")
  const manifestResult = rawManifest
    ? parseCanvasManifest(rawManifest, context.canvas, { repair: Boolean(normalizedPayload?.__nestedCanvasPayload) })
    : { manifest: null }

  if (manifestResult.error) {
    return {
      assistantText,
      canvas: manifestResult.canvas,
      offline: false,
      errorName: manifestResult.error.code,
    }
  }

  const manifest = manifestResult.manifest
  return {
    assistantText,
    canvas: manifest
      ? {
          manifest,
          parserState: normalizedPayload?.parser_state || null,
          domainOperations: normalizedPayload?.domain_operations || [],
          guardrails: normalizedPayload?.guardrails || [],
          errors: payloadErrors,
          lastUserText: context.userText || "",
        }
      : withRuntimeErrors(context.canvas, payloadErrors),
    offline: false,
  }
}

function unwrapNestedCanvasPayload(payload) {
  if (!payload || typeof payload !== "object") return payload
  let current = payload
  let didUnwrap = false
  for (let index = 0; index < 3; index += 1) {
    const nested = findNestedCanvasPayload(current)
    if (!nested) break
    current = mergeNestedPayload(current, nested)
    didUnwrap = true
  }
  return didUnwrap ? { ...current, __nestedCanvasPayload: true } : current
}

function findNestedCanvasPayload(payload) {
  for (const value of candidatePayloadStrings(payload)) {
    const nested = coerceCanvasPayload(extractJsonPayload(value))
    if (nested) return nested
  }
  const manifest = payload?.canvas_manifest || payload?.manifest
  if (typeof manifest === "string") return coerceCanvasPayload(extractJsonPayload(manifest))
  return null
}

function candidatePayloadStrings(payload) {
  const values = []
  for (const key of ["assistant_text", "message", "response", "text"]) {
    if (typeof payload?.[key] === "string") values.push(payload[key])
  }
  const manifest = payload?.canvas_manifest || payload?.manifest
  if (manifest && typeof manifest === "object") values.push(...canvasTextValues(manifest))
  return values
}

function canvasTextValues(value) {
  if (Array.isArray(value)) return value.flatMap(canvasTextValues)
  if (!value || typeof value !== "object") return []
  return Object.entries(value).flatMap(([key, nested]) => {
    if (["text", "message", "summary", "description", "content"].includes(key) && typeof nested === "string") {
      return [nested]
    }
    if (nested && typeof nested === "object") return canvasTextValues(nested)
    return []
  })
}

function coerceCanvasPayload(candidate) {
  if (!candidate || typeof candidate !== "object") return null
  if (candidate.canvas_manifest || candidate.manifest) return candidate
  if (candidate.id && candidate.type && candidate.title && Array.isArray(candidate.blocks) && Array.isArray(candidate.actions)) {
    return { assistant_text: "", canvas_manifest: candidate }
  }
  return null
}

function mergeNestedPayload(outer, nested) {
  return {
    ...nested,
    assistant_text: nested.assistant_text || outer.assistant_text || outer.message || outer.response || outer.text || "",
    parser_state: nested.parser_state || outer.parser_state || null,
    domain_operations: nested.domain_operations || outer.domain_operations || [],
    guardrails: nested.guardrails || outer.guardrails || [],
    errors: nested.errors || outer.errors || [],
  }
}

function extractJsonPayload(value) {
  const text = String(value || "").trim()
  if (!text) return null
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i)
  const source = fenced ? fenced[1].trim() : text.slice(Math.max(0, text.indexOf("{")), text.lastIndexOf("}") + 1)
  if (!source || !source.startsWith("{") || !source.endsWith("}")) return null
  try {
    return JSON.parse(source)
  } catch {
    return null
  }
}

function canvasTurnPayload({ userText, profile, canvas }) {
  return {
    user_text: userText,
    profile,
    canvas_manifest: canvas?.manifest || null,
  }
}

function parseCanvasManifest(rawManifest, canvas, options = {}) {
  try {
    const manifest = options.repair ? repairCanvasManifest(rawManifest) : rawManifest
    return { manifest: validateCanvasManifest(manifest) }
  } catch (error) {
    const contractError = {
      code: "model_contract_failed",
      message: error?.message || "CanvasManifest не прошел проверку.",
      status: 200,
    }
    return {
      manifest: null,
      canvas: withRuntimeError(canvas, contractError),
      error: contractError,
    }
  }
}

function repairCanvasManifest(rawManifest) {
  if (!rawManifest || typeof rawManifest !== "object") return rawManifest
  return {
    ...rawManifest,
    id: rawManifest.id || `canvas-${Date.now()}`,
    title: rawManifest.title || "Canvas",
    type: rawManifest.type || "custom",
    state: rawManifest.state || "review",
    blocks: Array.isArray(rawManifest.blocks) ? rawManifest.blocks.map(repairCanvasBlock) : [],
    actions: Array.isArray(rawManifest.actions) ? rawManifest.actions.map(repairDynamicAction) : [],
    dataSources: Array.isArray(rawManifest.dataSources) ? rawManifest.dataSources : [],
  }
}

function repairCanvasBlock(block, index) {
  if (!block || typeof block !== "object") {
    return { id: `block-${index + 1}`, type: "text", title: "", content: { text: String(block || "") } }
  }
  const content = block.content && typeof block.content === "object" && !Array.isArray(block.content)
    ? block.content
    : { text: String(block.content || block.text || block.message || "") }
  return {
    ...block,
    id: block.id || `block-${index + 1}`,
    type: block.type || "text",
    title: block.title || block.label || "",
    content,
  }
}

function repairDynamicAction(action, index) {
  if (!action || typeof action !== "object") {
    return {
      id: `action-${index + 1}`,
      label: `Action ${index + 1}`,
      icon: "spark",
      intent: `action.${index + 1}`,
      component: "button",
      payloadSchema: {},
      payload: {},
      risk: "safe",
      requiresConfirmation: false,
    }
  }
  const risk = ["safe", "review", "paid", "destructive"].includes(action.risk) ? action.risk : "safe"
  return {
    ...action,
    id: action.id || action.intent || `action-${index + 1}`,
    label: action.label || action.title || `Action ${index + 1}`,
    icon: action.icon || "spark",
    intent: action.intent || action.id || `action.${index + 1}`,
    component: action.component || "button",
    payloadSchema: action.payloadSchema && typeof action.payloadSchema === "object" ? action.payloadSchema : {},
    payload: action.payload && typeof action.payload === "object" ? action.payload : {},
    risk,
    requiresConfirmation: risk === "safe" ? Boolean(action.requiresConfirmation) : true,
  }
}

function aiEndpoint(path) {
  const configured = import.meta.env?.VITE_KOLIBRI_AI_ENDPOINT || globalThis.__KOLIBRI_AI_ENDPOINT__ || ""
  if (!configured) return path
  return configured.endsWith("/") ? `${configured.slice(0, -1)}${path}` : `${configured}${path}`
}

function safeLocalPath(path) {
  const value = String(path || "")
  if (!value.startsWith("/") || value.startsWith("//")) throw new Error("DynamicAction runtime path is not allowed")
  const parsed = new URL(value, "http://kolibri.local")
  if (CANVAS_RUNTIME_PATHS.has(parsed.pathname) || parsed.pathname.startsWith("/v1/factory/canvas")) {
    return `${parsed.pathname}${parsed.search}`
  }
  throw new Error("DynamicAction runtime path is not allowed")
}

function safeMethod(method) {
  const value = String(method || "GET").toUpperCase()
  if (["GET", "POST"].includes(value)) return value
  throw new Error("DynamicAction runtime method is not allowed")
}

function missingRuntimeResult(canvas) {
  return {
    assistantText: "",
    canvas,
    offline: true,
  }
}

function runtimeErrorResult(canvas, error) {
  return {
    assistantText: "",
    canvas: withRuntimeError(canvas, {
      code: "backend_offline",
      message: error?.name === "AbortError" ? "Запрос остановлен." : "Backend недоступен или не ответил.",
      status: 0,
    }),
    offline: true,
    errorName: error?.name || "RuntimeError",
  }
}

async function readErrorPayload(response) {
  try {
    return await response.json()
  } catch {
    return {}
  }
}

function apiErrorResult(canvas, response, payload) {
  const detail = payload?.detail || payload || {}
  const code = detail.code || httpErrorCode(response.status)
  const message = detail.message || detail.detail || response.statusText || "Ошибка API"
  return {
    assistantText: "",
    canvas: withRuntimeError(canvas, { code, message, status: response.status }),
    offline: response.status === 0 || response.status >= 500,
    errorName: code,
  }
}

function validationErrorResult(canvas, error) {
  return {
    assistantText: "",
    canvas: withRuntimeError(canvas, {
      code: "validation_failed",
      message: error?.message || "DynamicAction не прошел проверку.",
      status: 0,
    }),
    offline: false,
    errorName: "validation_failed",
  }
}

function withRuntimeError(canvas, error) {
  return withRuntimeErrors(canvas, [error])
}

function withRuntimeErrors(canvas, errors) {
  const normalized = normalizePayloadErrors(errors)
  if (!normalized.length) return canvas
  const existing = canvas || {}
  return {
    ...existing,
    runtimeStatus: normalized[0].code,
    errors: normalized,
  }
}

function normalizePayloadErrors(errors) {
  if (!Array.isArray(errors)) return []
  return errors.map(error => {
    if (typeof error === "string") {
      return {
        code: "api_error",
        message: error,
        status: 0,
        at: new Date().toISOString(),
      }
    }
    return {
      code: String(error?.code || "api_error"),
      message: String(error?.message || error?.detail || "Ошибка API"),
      status: Number(error?.status || 0),
      at: error?.at || new Date().toISOString(),
    }
  })
}

function httpErrorCode(status) {
  if (status === 402) return "payment_required"
  if (status === 409) return "confirmation_required"
  if (status === 422) return "validation_failed"
  if (status >= 500) return "model_contract_failed"
  return "api_error"
}

function normalizeBirdStatus(payload) {
  const metrics = payload?.metrics && typeof payload.metrics === "object" ? payload.metrics : {}
  const menu = Array.isArray(payload?.menu) ? payload.menu : []
  return {
    product: String(payload?.product || "Колибри"),
    state: safeBirdState(payload?.state),
    label: String(payload?.label || ""),
    summary: String(payload?.summary || ""),
    metrics: {
      queued_tasks: Number(metrics.queued_tasks || 0),
      running_tasks: Number(metrics.running_tasks || 0),
      active_agents: Number(metrics.active_agents || 0),
      total_agents: Number(metrics.total_agents || 0),
      quarantined_nodes: Number(metrics.quarantined_nodes || 0),
      dead_letter_tasks: Number(metrics.dead_letter_tasks || 0),
      failed_tasks: Number(metrics.failed_tasks || 0),
      active_leases: Number(metrics.active_leases || 0),
      global_max_inflight: Number(metrics.global_max_inflight || 0),
      approval_required: Boolean(metrics.approval_required),
    },
    menu: menu
      .filter(item => item && typeof item === "object")
      .map(item => ({ id: String(item.id || ""), label: String(item.label || "") }))
      .filter(item => item.id && item.label)
      .slice(0, 12),
    release: payload?.release && typeof payload.release === "object" ? payload.release : {},
    updated_at: Number(payload?.updated_at || Date.now() / 1000),
  }
}

function offlineBirdStatus(message) {
  return {
    product: "Колибри",
    state: "offline",
    label: "Офлайн",
    summary: String(message || "Backend недоступен."),
    metrics: {
      queued_tasks: 0,
      running_tasks: 0,
      active_agents: 0,
      total_agents: 0,
      quarantined_nodes: 0,
      dead_letter_tasks: 0,
      failed_tasks: 0,
      active_leases: 0,
      global_max_inflight: 0,
      approval_required: false,
    },
    menu: [],
    release: { ready: false, blocking_issues: 1 },
    updated_at: Date.now() / 1000,
  }
}

function safeBirdState(state) {
  const value = String(state || "ready")
  return ["ready", "thinking", "working", "syncing", "success", "attention", "error", "offline"].includes(value)
    ? value
    : "ready"
}

export const PRODUCT_STATES = [
  "empty",
  "listening",
  "thinking",
  "canvas_review",
  "editing",
  "exporting",
  "payment_required",
  "saved",
  "offline",
  "error",
]

export const COMPONENT_REGISTRY = {
  button: { surface: "composer", interactive: true },
  menu_item: { surface: "bird-menu", interactive: true },
  inline_chip: { surface: "chat", interactive: true },
  toolbar_action: { surface: "canvas-toolbar", interactive: true },
  bottom_action: { surface: "mobile-bottom-bar", interactive: true },
  canvas_block: { surface: "canvas", interactive: true },
  form_field: { surface: "canvas", interactive: true },
  file_card: { surface: "canvas", interactive: true },
  source_evidence_card: { surface: "canvas", interactive: true },
  diff_block: { surface: "canvas", interactive: true },
  confirm_block: { surface: "canvas", interactive: true },
  payment_gate: { surface: "canvas", interactive: true },
  offline_sync_state: { surface: "chat", interactive: false },
}

export const BLOCK_REGISTRY = {
  heading: { interactive: false },
  text: { interactive: false },
  table: { interactive: true },
  form: { interactive: true },
  checklist: { interactive: true },
  timeline: { interactive: false },
  source_evidence: { interactive: true },
  document_preview: { interactive: false },
  artifact_card: { interactive: true },
  diff: { interactive: true },
  confirmation: { interactive: true },
  payment_gate: { interactive: true },
  custom_data: { interactive: false },
}

export const RISK_LEVELS = ["safe", "review", "paid", "destructive"]

const SAFE_TOKEN = /^[a-zA-Z0-9_.:-]{1,80}$/
const MAX_VISIBLE_ACTIONS = 5
const TECHNICAL_ACTION_RE = /\b(api|json|schema|debug|runtime|internal|artifact|manifest|factory|ops)\b|артефакт|манифест|схема|отлад|служеб/i
const OPS_INTENT_RE = /^(factory|ops|debug|runtime|internal)\./i

export function createDynamicAction({
  id,
  label,
  icon = "spark",
  intent,
  component = "button",
  payloadSchema = {},
  payload = {},
  risk = "safe",
  requiresConfirmation = false,
  visibleWhen,
  disabledReason = "",
}) {
  const action = {
    id,
    label,
    icon,
    intent,
    component,
    payloadSchema,
    payload,
    risk,
    requiresConfirmation,
  }
  if (visibleWhen) action.visibleWhen = visibleWhen
  if (disabledReason) action.disabledReason = disabledReason
  return validateDynamicAction(action)
}

export function validateDynamicAction(action) {
  if (!action || typeof action !== "object") throw new Error("DynamicAction must be an object")
  if (!action.id || typeof action.id !== "string") throw new Error("DynamicAction.id is required")
  if (!action.label || typeof action.label !== "string") throw new Error(`DynamicAction ${action.id} label is required`)
  if (!action.intent || typeof action.intent !== "string") throw new Error(`DynamicAction ${action.id} intent is required`)
  if (!COMPONENT_REGISTRY[action.component]) throw new Error(`DynamicAction ${action.id} uses unsupported component`)
  if (!RISK_LEVELS.includes(action.risk)) throw new Error(`DynamicAction ${action.id} uses unsupported risk`)
  if (action.risk !== "safe" && !action.requiresConfirmation) {
    throw new Error(`DynamicAction ${action.id} non-safe actions require confirmation`)
  }
  const serialized = JSON.stringify(action)
  if (/<script|javascript:|onerror=|onclick=|eval\(|new Function/i.test(serialized)) {
    throw new Error(`DynamicAction ${action.id} contains unsafe executable content`)
  }
  return Object.freeze({ ...action })
}

export function validateCanvasManifest(manifest) {
  if (!manifest || typeof manifest !== "object") throw new Error("CanvasManifest must be an object")
  if (!manifest.id || !manifest.title) throw new Error("CanvasManifest id and title are required")
  if (!manifest.type || !SAFE_TOKEN.test(String(manifest.type))) throw new Error("CanvasManifest.type must be a safe token")
  const blocks = Array.isArray(manifest.blocks) ? manifest.blocks : []
  const actions = Array.isArray(manifest.actions) ? manifest.actions : []
  const dataSources = Array.isArray(manifest.dataSources) ? manifest.dataSources : []
  blocks.forEach(block => validateCanvasBlock(block))
  return {
    ...manifest,
    blocks,
    actions: actions.map(validateDynamicAction),
    dataSources,
    version: Number(manifest.version || 1),
    updatedAt: manifest.updatedAt || new Date().toISOString(),
  }
}

export function validateCanvasBlock(block) {
  if (!block || typeof block !== "object") throw new Error("CanvasBlock must be an object")
  if (!block.id || typeof block.id !== "string") throw new Error("CanvasBlock.id is required")
  if (!BLOCK_REGISTRY[block.type]) throw new Error(`CanvasBlock ${block.id} uses unsupported type ${block.type}`)
  const serialized = JSON.stringify(block)
  if (/<script|javascript:|onerror=|onclick=|eval\(|new Function|dangerouslySetInnerHTML/i.test(serialized)) {
    throw new Error(`CanvasBlock ${block.id} contains unsafe executable content`)
  }
  return true
}

export function visibleActions(manifest, context = {}) {
  if (!manifest?.actions) return []
  const seen = new Set()
  return manifest.actions
    .filter(action => isUserFacingAction(action, context))
    .filter(action => isRelevantForState(action, manifest, context))
    .map(normalizeVisibleAction)
    .filter(action => {
      const key = action.label.toLowerCase()
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .slice(0, Number(context.maxActions || MAX_VISIBLE_ACTIONS))
}

function isRelevantForState(action, manifest, context) {
  const state = String(context.state || manifest?.state || "")
  const risk = String(action.risk || "safe")
  const intent = String(action.intent || "")
  if (risk !== "safe" && context.actionGroup && context.actionGroup !== risk) return false
  if (risk !== "safe" && !context.actionGroup && !isGuardedRiskRelevant(risk, state, action)) return false
  if (state === "exporting" && !/stop|cancel|status|download|retry|отмен|статус|скач/i.test(`${intent} ${action.label}`)) return false
  if (state === "offline" && !/retry|sync|local|import|повтор|синх|локаль|импорт/i.test(`${intent} ${action.label}`)) return false
  if (state === "ready" && /clarify|уточ/i.test(`${intent} ${action.label}`)) return false
  return true
}

function isGuardedRiskRelevant(risk, state, action) {
  const text = `${action.intent || ""} ${action.label || ""}`
  if (risk === "review") return /review|canvas_review|editing|draft|diff|провер|примен|правк|пересч/i.test(`${state} ${text}`)
  if (risk === "paid") return /payment|required|export|ready|pdf|pack|доступ|оплат|pdf|пакет|экспорт/i.test(`${state} ${text}`)
  return false
}

function isUserFacingAction(action, context) {
  if (!action || typeof action !== "object") return false
  if (action.disabledReason) return false
  if (action.visibleWhen && !Object.entries(action.visibleWhen).every(([key, value]) => context[key] === value)) return false
  const label = String(action.label || "").trim()
  const intent = String(action.intent || "")
  const id = String(action.id || "")
  if (!label || label.length > 34) return false
  if (!context.opsMode && (OPS_INTENT_RE.test(intent) || OPS_INTENT_RE.test(id))) return false
  if (!context.opsMode && TECHNICAL_ACTION_RE.test(`${label} ${intent} ${id}`)) return false
  if (!["button", "menu_item", "inline_chip", "toolbar_action", "bottom_action", "canvas_block"].includes(action.component)) return false
  return true
}

function normalizeVisibleAction(action) {
  const label = String(action.label || "").trim().replace(/\s+/g, " ")
  return {
    ...action,
    label: label.length > 22 ? `${label.slice(0, 21)}…` : label,
  }
}

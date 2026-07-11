const IS_PAGES = typeof window !== "undefined" && window.location.hostname.includes("github.io");
const RUNTIME_API_BASE = typeof window !== "undefined" ? window.__KOLIBRI_CONFIG__?.apiBase : "";
const BUILD_API_BASE = import.meta.env?.VITE_API_BASE || "";
// Production and the Home kiosk use a same-origin gateway. Vite development
// also stays same-origin and relies on vite.config.js proxying /api and /v1.
export const API_BASE = RUNTIME_API_BASE || BUILD_API_BASE || (IS_PAGES ? "https://kolibriai.ru" : "");

export const API_ENDPOINTS = Object.freeze({
  // All Shell dialogue and typed work uses the canonical OpenAI-compatible
  // Responses API. Compatibility aliases remain server-side only.
  response: "/v1/responses",
  publicSession: "/v1/public/session",
  status: ["/api/factory/status", "/v1/health", "/api/health"],
  tasks: ["/v1/tasks?limit=250"],
  nodes: ["/v1/nodes?limit=250", "/v1/fleet/nodes", "/api/factory/roster"],
  models: ["/v1/models", "/api/models"],
  capabilities: ["/v1/capabilities", "/v1/os/capabilities"],
  approvals: ["/v1/approvals?limit=100"],
  browserSessions: "/v1/browser-sessions",
  automationValidate: "/v1/automations/validate",
});

export class KolibriApiError extends Error {
  constructor(message, { status = 0, endpoint = "", payload = null } = {}) {
    super(message);
    this.name = "KolibriApiError";
    this.status = status;
    this.endpoint = endpoint;
    this.payload = payload;
  }
}

async function requestJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "same-origin",
    headers: options.body instanceof FormData ? options.headers : { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new KolibriApiError(payload?.detail || payload?.error?.message || payload?.error || `HTTP ${response.status}`, {
      status: response.status,
      endpoint: path,
      payload,
    });
  }
  return { payload, endpoint: path, status: response.status };
}

async function firstAvailable(paths, options = {}) {
  const attempts = [];
  for (const path of paths) {
    try {
      return await requestJson(path, options);
    } catch (error) {
      attempts.push(error);
      if (error.status === 401 || error.status === 403) throw error;
    }
  }
  const last = attempts.at(-1);
  throw new KolibriApiError(last?.message || "Совместимый API пока недоступен", {
    status: last?.status,
    endpoint: last?.endpoint,
    payload: { attempts: attempts.map((error) => ({ endpoint: error.endpoint, status: error.status })) },
  });
}

let publicSessionPromise = null;
let publicSessionRefreshPromise = null;
let publicSessionGeneration = 0;

export function resetPublicSessionForTests() {
  publicSessionPromise = null;
  publicSessionRefreshPromise = null;
  publicSessionGeneration = 0;
}

function publicSessionExpired(error) {
  if (!(error instanceof KolibriApiError) || error.status !== 401) return false;
  const markers = [
    error.payload?.detail,
    error.payload?.detail?.code,
    error.payload?.error,
    error.payload?.error?.code,
    error.message,
  ];
  return markers.some((marker) => marker === "public_session_required_or_expired");
}

function assertPublicSession(result) {
  if (result.payload?.object !== "public.session") {
    throw new KolibriApiError("Сервер не выдал безопасную сессию", {
      status: result.status,
      endpoint: API_ENDPOINTS.publicSession,
    });
  }
  return result.payload;
}

async function createPublicSession() {
  return assertPublicSession(await requestJson(API_ENDPOINTS.publicSession, {
    method: "POST",
    body: JSON.stringify({}),
  }));
}

export async function ensurePublicSession() {
  if (publicSessionRefreshPromise) return publicSessionRefreshPromise;
  if (publicSessionPromise) return publicSessionPromise;
  const sessionPromise = (async () => {
    try {
      // Session discovery is shared by every in-flight Shell request.  A
      // caller-specific AbortSignal must not cancel that shared handshake and
      // poison unrelated requests; the signal remains scoped to /responses.
      const current = await requestJson(API_ENDPOINTS.publicSession);
      if (current.payload?.object === "public.session") return current.payload;
    } catch (error) {
      if (!(error instanceof KolibriApiError) || error.status !== 401) throw error;
    }
    return createPublicSession();
  })().then((session) => {
    publicSessionGeneration += 1;
    return session;
  }).catch((error) => {
    if (publicSessionPromise === sessionPromise) publicSessionPromise = null;
    throw error;
  });
  publicSessionPromise = sessionPromise;
  return publicSessionPromise;
}

async function refreshPublicSession(observedGeneration) {
  // Another request may already have replaced the expired cookie while this
  // request's 401 was in flight. In that case, reuse the newer session rather
  // than issuing another POST and invalidating concurrent retries.
  if (observedGeneration !== publicSessionGeneration && publicSessionPromise) {
    return publicSessionPromise;
  }
  if (publicSessionRefreshPromise) return publicSessionRefreshPromise;

  publicSessionPromise = null;
  const refreshPromise = createPublicSession().then((session) => {
    publicSessionGeneration += 1;
    publicSessionPromise = Promise.resolve(session);
    return session;
  }).finally(() => {
    if (publicSessionRefreshPromise === refreshPromise) publicSessionRefreshPromise = null;
  });
  publicSessionRefreshPromise = refreshPromise;
  return refreshPromise;
}

function parseSseBlock(block) {
  let event = "message";
  const data = [];
  for (const rawLine of block.split(/\r?\n/)) {
    if (!rawLine || rawLine.startsWith(":")) continue;
    const separator = rawLine.indexOf(":");
    const field = separator === -1 ? rawLine : rawLine.slice(0, separator);
    const value = separator === -1 ? "" : rawLine.slice(separator + 1).replace(/^ /, "");
    if (field === "event") event = value;
    if (field === "data") data.push(value);
  }
  if (!data.length) return null;
  try {
    return { event, data: JSON.parse(data.join("\n")) };
  } catch {
    throw new KolibriApiError("Responses SSE вернул повреждённое событие", {
      status: 502,
      endpoint: API_ENDPOINTS.response,
    });
  }
}

async function consumeResponsesSse(response) {
  let buffer = "";
  let streamedText = "";
  let completed = null;

  const acceptBlock = (block) => {
    const parsed = parseSseBlock(block);
    if (!parsed) return;
    const payload = parsed.data;
    const type = payload?.type || parsed.event;
    if (type === "response.output_text.delta" && typeof payload.delta === "string") {
      streamedText += payload.delta;
    } else if (type === "response.completed" && payload.response) {
      completed = payload.response;
    } else if (type === "response.failed" || type === "error") {
      const failed = payload.response || payload;
      throw new KolibriApiError(
        failed?.error?.message || payload?.message || "Kolibri could not produce a verified response",
        { status: 503, endpoint: API_ENDPOINTS.response, payload: failed },
      );
    }
  };

  const flush = (final = false) => {
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = final ? "" : blocks.pop() || "";
    for (const block of blocks) if (block.trim()) acceptBlock(block);
    if (final && buffer.trim()) acceptBlock(buffer);
  };

  if (response.body?.getReader) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      flush(false);
    }
    buffer += decoder.decode();
    flush(true);
  } else {
    buffer = await response.text();
    flush(true);
  }
  if (!completed) {
    throw new KolibriApiError("Responses SSE завершился без response.completed", {
      status: 502,
      endpoint: API_ENDPOINTS.response,
    });
  }
  const finalText = extractResponseText(completed);
  if (!finalText || (streamedText && streamedText !== finalText)) {
    throw new KolibriApiError("Ответ SSE не прошёл проверку целостности", {
      status: 502,
      endpoint: API_ENDPOINTS.response,
    });
  }
  return completed;
}

async function requestResponsesStream(body, idempotencyKey, signal) {
  const response = await fetch(`${API_BASE}${API_ENDPOINTS.response}`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new KolibriApiError(
      payload?.detail || payload?.error?.message || `HTTP ${response.status}`,
      { status: response.status, endpoint: API_ENDPOINTS.response, payload },
    );
  }
  if (!String(response.headers?.get?.("content-type") || "").includes("text/event-stream")) {
    throw new KolibriApiError("Responses API не включил SSE", {
      status: 502,
      endpoint: API_ENDPOINTS.response,
    });
  }
  return consumeResponsesSse(response);
}

function unwrapData(payload) {
  if (!payload || typeof payload !== "object") return payload;
  return payload.data && typeof payload.data === "object" ? payload.data : payload;
}

export function normalizeTasks(payload) {
  const data = unwrapData(payload);
  const tasks = Array.isArray(data) ? data : Array.isArray(data?.tasks) ? data.tasks : Array.isArray(data?.items) ? data.items : [];
  return tasks.filter(Boolean).map((task) => ({
    ...task,
    task_id: task.task_id || task.id || task.trace_id || "",
    state: task.state || task.status || "unknown",
    title: task.title || task.name || task.envelope?.title || task.envelope?.objective || task.envelope?.kind || task.kind || "Задача",
  }));
}

export function normalizeNodes(payload) {
  const data = unwrapData(payload);
  const raw = data?.nodes || data?.servers || payload?.nodes || payload?.servers || [];
  if (Array.isArray(raw)) return raw.filter(Boolean);
  if (raw && typeof raw === "object") return Object.entries(raw).map(([id, node]) => ({ node_id: node?.node_id || id, ...node }));
  return [];
}

export function normalizeModels(payload) {
  const data = unwrapData(payload);
  const candidates = [payload?.data, data?.data, data?.models, payload?.models, data, payload];
  return candidates.find(Array.isArray) || [];
}

export function normalizeCapabilities(payload) {
  if (Array.isArray(payload?.data)) return payload.data;
  if (Array.isArray(payload?.capabilities)) return payload.capabilities;
  const data = unwrapData(payload);
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.capabilities)) return data.capabilities;
  return [];
}

function resultFromSettled(result, normalizer = (value) => value) {
  if (result.status === "rejected") return { available: false, value: null, endpoint: result.reason?.endpoint || "", error: result.reason?.message || "API недоступен", status: result.reason?.status || 0 };
  return { available: true, value: normalizer(result.value.payload), endpoint: result.value.endpoint, error: "", status: result.value.status };
}

export async function loadControlSnapshot(signal) {
  const requests = [
    firstAvailable(API_ENDPOINTS.status, { signal }),
    firstAvailable(API_ENDPOINTS.tasks, { signal }),
    firstAvailable(API_ENDPOINTS.nodes, { signal }),
    firstAvailable(API_ENDPOINTS.models, { signal }),
    firstAvailable(API_ENDPOINTS.capabilities, { signal }),
    firstAvailable(API_ENDPOINTS.approvals, { signal }),
  ];
  const [status, tasks, nodes, models, capabilities, approvals] = await Promise.allSettled(requests);
  return {
    status: resultFromSettled(status, unwrapData),
    tasks: resultFromSettled(tasks, normalizeTasks),
    nodes: resultFromSettled(nodes, normalizeNodes),
    models: resultFromSettled(models, normalizeModels),
    capabilities: resultFromSettled(capabilities, normalizeCapabilities),
    approvals: resultFromSettled(approvals, (payload) => unwrapData(payload)?.approvals || unwrapData(payload)?.items || []),
    fetchedAt: new Date().toISOString(),
  };
}

function executionModesFromCatalog(payload) {
  const data = unwrapData(payload);
  const advertised = [
    ...(Array.isArray(payload?.supported_execution_modes) ? payload.supported_execution_modes : []),
    ...(Array.isArray(data?.supported_execution_modes) ? data.supported_execution_modes : []),
    ...normalizeModels(payload).flatMap((model) => Array.isArray(model?.supported_execution_modes) ? model.supported_execution_modes : []),
  ];
  return [...new Set(advertised.filter((mode) => ["fast", "codex"].includes(mode)))];
}

export async function loadSupportedExecutionModes(signal) {
  const primary = await firstAvailable(API_ENDPOINTS.models, { signal, cache: "no-store" });
  let supported = executionModesFromCatalog(primary.payload);

  // A retired service worker used to cache every /v1/* GET, including the
  // model catalog. During its final controlled page lifetime it can still
  // return an older successful /v1/models response. Confirm a catalog that
  // omits Codex through the uncached /api compatibility route before hiding
  // the mode; /api/* was explicitly excluded by that worker.
  const compatibilityPath = API_ENDPOINTS.models.find((path) => path !== primary.endpoint);
  if (!supported.includes("codex") && compatibilityPath) {
    try {
      const compatibility = await requestJson(compatibilityPath, { signal, cache: "no-store" });
      supported = [...new Set([...supported, ...executionModesFromCatalog(compatibility.payload)])];
    } catch (error) {
      if (signal?.aborted || error?.name === "AbortError") throw error;
    }
  }

  return supported.includes("fast") ? supported : ["fast", ...supported];
}

function extractResponseText(payload) {
  if (!payload || typeof payload !== "object") return "";
  if (typeof payload.response === "string") return payload.response;
  if (typeof payload.output_text === "string") return payload.output_text;
  if (Array.isArray(payload.output)) {
    for (const item of payload.output) {
      if (typeof item?.content === "string") return item.content;
      if (Array.isArray(item?.content)) {
        const text = item.content.map((entry) => entry?.text || entry?.content || "").join("");
        if (text) return text;
      }
    }
  }
  return payload.choices?.[0]?.message?.content || payload.choices?.[0]?.text || payload.assistant_message?.content || "";
}

const CONVERSATION_MAX_MESSAGES = 24;
const CONVERSATION_MAX_BYTES = 256 * 1024;
const CONVERSATION_ROLES = new Set(["user", "assistant"]);

function messageBytes(message) {
  return new TextEncoder().encode(`${message.role}\n${message.content}`).byteLength;
}

export function buildConversationMessages(history, currentText) {
  const prompt = nonEmptyText(currentText, "request.text");
  const normalized = (Array.isArray(history) ? history : [])
    .filter((message) => message && CONVERSATION_ROLES.has(message.role) && !["running", "failed"].includes(message.status))
    .map((message) => ({
      role: message.role,
      content: String(message.content ?? message.text ?? "").replaceAll("\u0000", "").trim(),
    }))
    .filter((message) => message.content);
  const current = { role: "user", content: prompt };
  const selected = [current];
  let bytes = messageBytes(current);

  for (let index = normalized.length - 1; index >= 0 && selected.length < CONVERSATION_MAX_MESSAGES; index -= 1) {
    const candidate = normalized[index];
    const size = messageBytes(candidate);
    if (bytes + size > CONVERSATION_MAX_BYTES) continue;
    selected.push(candidate);
    bytes += size;
  }
  return selected.reverse();
}

const PUBLIC_TASK_SCHEMA = "kolibri.public-task.v1";
const PUBLIC_TASK_INTENTS = Object.freeze(["estimate", "document", "site", "app"]);
const SHA256 = /^[a-f0-9]{64}$/i;
const SAFE_ARTIFACT_SCHEMES = /^(?:artifact:|https?:|\/)/i;
const SECRET_KEYS = new Set([
  "access_token",
  "api_key",
  "apikey",
  "authorization",
  "client_secret",
  "cookie",
  "credentials",
  "password",
  "private_key",
  "refresh_token",
  "secret",
  "secret_key",
  "session_cookie",
  "token",
  "webhook_secret",
]);
const SECRET_SUFFIXES = [
  "_access_token",
  "_api_key",
  "_authorization",
  "_client_secret",
  "_cookie",
  "_password",
  "_private_key",
  "_refresh_token",
  "_secret",
  "_session_cookie",
  "_token",
  "_webhook_secret",
];
const ROUTING_FIELDS = new Set([
  "provider",
  "provider_id",
  "provider_model",
  "model",
  "runner",
  "runner_id",
  "control_plane",
  "control_plane_url",
]);
const TASK_FIELDS = Object.freeze({
  estimate: new Set(["intent", "brief", "region", "spec", "requested_artifacts"]),
  document: new Set(["intent", "brief", "document_type", "format", "content"]),
  site: new Set(["intent", "brief", "target", "requirements", "requested_artifacts"]),
  app: new Set(["intent", "brief", "target", "requirements", "requested_artifacts"]),
});

function normalizedKey(value) {
  return String(value)
    .trim()
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/[^a-z0-9]+/gi, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
}

function isSecretKey(value) {
  const key = normalizedKey(value);
  return SECRET_KEYS.has(key) || SECRET_SUFFIXES.some((suffix) => key.endsWith(suffix));
}

function clonePublicValue(value, path = "task", depth = 0) {
  if (depth > 10) throw new KolibriApiError(`${path}: превышена допустимая вложенность`);
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new KolibriApiError(`${path}: число должно быть конечным`);
    return value;
  }
  if (Array.isArray(value)) return value.map((item, index) => clonePublicValue(item, `${path}[${index}]`, depth + 1));
  if (value && typeof value === "object" && Object.getPrototypeOf(value) === Object.prototype) {
    const result = {};
    for (const [key, child] of Object.entries(value)) {
      if (isSecretKey(key)) {
        throw new KolibriApiError(`${path}.${key}: передавайте ссылку на credential, а не секрет`);
      }
      result[key] = clonePublicValue(child, `${path}.${key}`, depth + 1);
    }
    return result;
  }
  throw new KolibriApiError(`${path}: неподдерживаемое значение`);
}

function nonEmptyText(value, label, maxLength = 50_000) {
  const text = typeof value === "string" ? value.trim() : "";
  if (!text || text.length > maxLength) throw new KolibriApiError(`${label}: требуется текст до ${maxLength} символов`);
  return text;
}

function enumValue(value, allowed, label) {
  if (!allowed.includes(value)) throw new KolibriApiError(`${label}: неподдерживаемое значение`);
  return value;
}

function integerInRange(value, minimum, maximum, label) {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    throw new KolibriApiError(`${label}: требуется целое число от ${minimum} до ${maximum}`);
  }
  return value;
}

function currencyCode(value) {
  if (typeof value !== "string" || !/^[A-Z]{3}$/.test(value)) {
    throw new KolibriApiError("estimate.currency: требуется трёхбуквенный ISO-код");
  }
  return value;
}

function requestedArtifacts(value, allowed, defaults, minimum = 0) {
  const list = value === undefined ? defaults : value;
  if (!Array.isArray(list) || list.length < minimum || list.length > allowed.length || new Set(list).size !== list.length) {
    throw new KolibriApiError("requested_artifacts: некорректный список результатов");
  }
  for (const item of list) enumValue(item, allowed, "requested_artifacts");
  return [...list];
}

function assertNoRoutingSelection(value, label = "task") {
  for (const key of Object.keys(value || {})) {
    if (ROUTING_FIELDS.has(normalizedKey(key))) {
      throw new KolibriApiError(`${label}.${key}: исполнитель выбирается Kolibri внутри gateway`);
    }
  }
}

function normalizeTaskForTransport(task) {
  if (!task || typeof task !== "object" || Array.isArray(task)) throw new KolibriApiError("task: требуется typed task");
  assertNoRoutingSelection(task);
  const intent = enumValue(task.intent, PUBLIC_TASK_INTENTS, "task.intent");
  const allowed = TASK_FIELDS[intent];
  for (const key of Object.keys(task)) {
    if (!allowed.has(key)) throw new KolibriApiError(`task.${key}: поле не входит в публичный typed contract`);
  }
  return clonePublicValue(task);
}

/** Build a side-effect-free estimate request. Money is calculated by the
 * backend deterministic decimal/minor-unit engine, never in the browser or by
 * an LLM. */
export function buildDeterministicEstimateTask({
  title,
  currency = "RUB",
  minorUnit = 2,
  region = "Не указан",
  clientName = null,
  objectName = null,
  objectAddress = null,
  sourceSummary = "Цены требуют проверки перед коммерческим использованием",
  assumptions = [],
  questions = [],
  lines,
  overheadRateBps = 0,
  taxRateBps = 0,
  requestedArtifacts: artifactKinds = [],
  ...routingOrUnknown
} = {}) {
  assertNoRoutingSelection(routingOrUnknown, "estimate");
  if (Object.keys(routingOrUnknown).length) throw new KolibriApiError(`estimate.${Object.keys(routingOrUnknown)[0]}: неизвестное поле`);
  if (!Array.isArray(lines) || lines.length < 1 || lines.length > 2_000) {
    throw new KolibriApiError("estimate.lines: требуется от 1 до 2000 строк");
  }
  const ids = new Set();
  const normalizedLines = lines.map((line, index) => {
    if (!line || typeof line !== "object" || Array.isArray(line)) throw new KolibriApiError(`estimate.lines[${index}]: требуется строка сметы`);
    assertNoRoutingSelection(line, `estimate.lines[${index}]`);
    const allowed = new Set(["id", "section", "description", "category", "unit", "quantity", "unitPriceMinor", "unit_price_minor", "provenance"]);
    for (const key of Object.keys(line)) if (!allowed.has(key)) throw new KolibriApiError(`estimate.lines[${index}].${key}: неизвестное поле`);
    const id = nonEmptyText(line.id, `estimate.lines[${index}].id`, 200);
    if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{1,199}$/.test(id)) throw new KolibriApiError(`estimate.lines[${index}].id: недопустимый идентификатор`);
    if (ids.has(id)) throw new KolibriApiError(`estimate.lines[${index}].id: идентификатор должен быть уникальным`);
    ids.add(id);
    const quantity = String(line.quantity ?? "").trim();
    if (!/^(?:0|[1-9]\d{0,17})(?:\.\d{1,6})?$/.test(quantity) || Number(quantity) <= 0) {
      throw new KolibriApiError(`estimate.lines[${index}].quantity: требуется положительное десятичное число`);
    }
    const provenance = clonePublicValue(line.provenance || { source: "manual" }, `estimate.lines[${index}].provenance`);
    const provenanceKeys = new Set(["source", "source_ref", "captured_at"]);
    for (const key of Object.keys(provenance)) if (!provenanceKeys.has(key)) throw new KolibriApiError(`estimate.lines[${index}].provenance.${key}: неизвестное поле`);
    provenance.source = enumValue(provenance.source || "manual", ["manual", "assumption", "catalog", "contract", "supplier", "measurement"], `estimate.lines[${index}].provenance.source`);
    return {
      id,
      section: nonEmptyText(line.section || "Основные работы", `estimate.lines[${index}].section`, 200),
      description: nonEmptyText(line.description, `estimate.lines[${index}].description`, 1_000),
      category: enumValue(line.category || "other", ["labor", "material", "equipment", "service", "other"], `estimate.lines[${index}].category`),
      unit: nonEmptyText(line.unit || "unit", `estimate.lines[${index}].unit`, 40),
      quantity,
      unit_price_minor: integerInRange(line.unitPriceMinor ?? line.unit_price_minor, 0, 10 ** 15, `estimate.lines[${index}].unit_price_minor`),
      provenance,
    };
  });
  return {
    intent: "estimate",
    spec: {
      title: nonEmptyText(title, "estimate.title", 500),
      currency: currencyCode(currency),
      minor_unit: enumValue(minorUnit, [0, 2, 3], "estimate.minor_unit"),
      region: nonEmptyText(region || "Не указан", "estimate.region", 300),
      ...(clientName ? { client_name: nonEmptyText(clientName, "estimate.client_name", 300) } : {}),
      ...(objectName ? { object_name: nonEmptyText(objectName, "estimate.object_name", 500) } : {}),
      ...(objectAddress ? { object_address: nonEmptyText(objectAddress, "estimate.object_address", 1_000) } : {}),
      source_summary: nonEmptyText(sourceSummary, "estimate.source_summary", 2_000),
      assumptions: clonePublicValue(assumptions, "estimate.assumptions"),
      questions: clonePublicValue(questions, "estimate.questions"),
      lines: normalizedLines,
      overhead_rate_bps: integerInRange(overheadRateBps, 0, 10_000, "estimate.overhead_rate_bps"),
      tax_rate_bps: integerInRange(taxRateBps, 0, 10_000, "estimate.tax_rate_bps"),
    },
    requested_artifacts: requestedArtifacts(artifactKinds, ["pdf", "pdf-x", "xlsx", "docx"], []),
  };
}

// Short public name for composer integrations; the longer name documents the
// money-authority invariant at the implementation boundary.
export const buildEstimateTask = buildDeterministicEstimateTask;

export function buildEstimateProposalTask({ brief, region = "", requestedArtifacts: artifactKinds = ["pdf"], ...routingOrUnknown } = {}) {
  assertNoRoutingSelection(routingOrUnknown, "estimate");
  if (Object.keys(routingOrUnknown).length) throw new KolibriApiError(`estimate.${Object.keys(routingOrUnknown)[0]}: неизвестное поле`);
  return {
    intent: "estimate",
    brief: nonEmptyText(brief, "estimate.brief"),
    ...(region.trim() ? { region: nonEmptyText(region, "estimate.region", 300) } : {}),
    requested_artifacts: requestedArtifacts(artifactKinds, ["pdf", "pdf-x", "xlsx", "docx"], ["pdf"]),
  };
}

export function buildDocumentTask({ brief, documentType = "custom", format = "pdf", content = {}, ...routingOrUnknown } = {}) {
  assertNoRoutingSelection(routingOrUnknown, "document");
  if (Object.keys(routingOrUnknown).length) throw new KolibriApiError(`document.${Object.keys(routingOrUnknown)[0]}: неизвестное поле`);
  return {
    intent: "document",
    brief: nonEmptyText(brief, "document.brief"),
    document_type: enumValue(documentType, ["commercial-offer", "contract", "completion-act", "invoice", "report", "custom"], "document.document_type"),
    format: enumValue(format, ["pdf", "pdf-x", "xlsx", "docx", "html", "text"], "document.format"),
    content: clonePublicValue(content, "document.content"),
  };
}

export function buildSiteTask({ brief, target = "website", requirements = {}, requestedArtifacts: artifactKinds, ...routingOrUnknown } = {}) {
  assertNoRoutingSelection(routingOrUnknown, "site");
  if (Object.keys(routingOrUnknown).length) throw new KolibriApiError(`site.${Object.keys(routingOrUnknown)[0]}: неизвестное поле`);
  return {
    intent: "site",
    brief: nonEmptyText(brief, "site.brief"),
    target: enumValue(target, ["website", "webapp"], "site.target"),
    requirements: clonePublicValue(requirements, "site.requirements"),
    requested_artifacts: requestedArtifacts(artifactKinds, ["source", "site-preview", "test-report"], ["source", "site-preview"], 1),
  };
}

export function buildAppTask({ brief, target = "web", requirements = {}, requestedArtifacts: artifactKinds, ...routingOrUnknown } = {}) {
  assertNoRoutingSelection(routingOrUnknown, "app");
  if (Object.keys(routingOrUnknown).length) throw new KolibriApiError(`app.${Object.keys(routingOrUnknown)[0]}: неизвестное поле`);
  return {
    intent: "app",
    brief: nonEmptyText(brief, "app.brief"),
    target: enumValue(target, ["web", "linux", "container", "android", "ios", "macos"], "app.target"),
    requirements: clonePublicValue(requirements, "app.requirements"),
    requested_artifacts: requestedArtifacts(artifactKinds, ["source", "build", "test-report", "app-preview"], ["source", "build", "test-report"], 1),
  };
}

function safeArtifact(artifact, delivered) {
  if (!artifact || typeof artifact !== "object" || artifact.status !== "materialized") return null;
  const referenceSha = String(artifact.reference_sha256 || "").toLowerCase();
  const contentSha = String(artifact.content_sha256 || "").toLowerCase();
  const bindingSha = String(artifact.evidence_binding_sha256 || "").toLowerCase();
  const deliverableType = typeof artifact.deliverable_type === "string" ? artifact.deliverable_type : "";
  if (!SHA256.test(referenceSha) || !SHA256.test(contentSha) || !SHA256.test(bindingSha)) return null;
  if (!Number.isSafeInteger(artifact.size_bytes) || artifact.size_bytes < 0 || !delivered.has(deliverableType)) return null;
  if (artifact.locator && (typeof artifact.locator !== "string" || !SAFE_ARTIFACT_SCHEMES.test(artifact.locator))) return null;
  const result = {
    reference_sha256: referenceSha,
    content_sha256: contentSha,
    size_bytes: artifact.size_bytes,
    deliverable_type: deliverableType,
    evidence_binding_sha256: bindingSha,
    status: "materialized",
  };
  if (typeof artifact.id === "string" && artifact.id) result.id = artifact.id;
  if (artifact.immutable === true) result.immutable = true;
  if (typeof artifact.estimate_id === "string" && artifact.estimate_id) result.estimate_id = artifact.estimate_id;
  if (Number.isSafeInteger(artifact.estimate_version) && artifact.estimate_version > 0) result.estimate_version = artifact.estimate_version;
  for (const key of ["kind", "name", "locator", "origin", "media_type"]) {
    if (typeof artifact[key] === "string" && artifact[key]) result[key] = artifact[key];
  }
  return result;
}

export function normalizeTypedTaskEnvelope(task, expectedIntent = "") {
  if (!task || typeof task !== "object" || task.schema_version !== PUBLIC_TASK_SCHEMA) {
    throw new KolibriApiError("Typed gateway не вернул контракт Kolibri public-task.v1", { status: 502 });
  }
  const intent = enumValue(task.intent, PUBLIC_TASK_INTENTS, "task.intent");
  if (expectedIntent && intent !== expectedIntent) throw new KolibriApiError("Typed gateway вернул результат другой задачи", { status: 502 });
  const execution = task.execution && typeof task.execution === "object" ? task.execution : {};
  const providerVerified = execution.provider_verified === true && execution.status === "completed" && execution.model === "kolibri";
  const delivery = task.artifact_delivery && typeof task.artifact_delivery === "object" ? task.artifact_delivery : {};
  const requested = Array.isArray(delivery.requested) ? [...new Set(delivery.requested.filter((item) => typeof item === "string" && item))] : [];
  const reportedDelivered = new Set(Array.isArray(delivery.delivered) ? delivery.delivered.filter((item) => requested.includes(item)) : []);
  const artifacts = providerVerified && Array.isArray(task.artifacts)
    ? task.artifacts.map((artifact) => safeArtifact(artifact, reportedDelivered)).filter(Boolean)
    : [];
  const delivered = [...new Set(artifacts.map((artifact) => artifact.deliverable_type))].sort();
  const missing = requested.filter((item) => !delivered.includes(item));
  const serverStatus = ["completed", "incomplete", "failed"].includes(task.status) ? task.status : "failed";
  const status = !providerVerified || serverStatus === "failed"
    ? "failed"
    : serverStatus === "completed" && missing.length === 0
      ? "completed"
      : "incomplete";
  let result = null;
  if (status !== "failed" && intent === "estimate") {
    const calculation = task.result?.type === "deterministic_estimate"
      ? clonePublicValue(task.result.calculation, "task.result.calculation")
      : null;
    if (!calculation || calculation.money_authority !== "deterministic_calculator" || calculation.llm_calculates_money !== false) {
      throw new KolibriApiError("Смета не подтверждена детерминированным расчётным контуром", { status: 502 });
    }
    const estimate = task.result?.estimate && typeof task.result.estimate === "object"
      ? clonePublicValue(task.result.estimate, "task.result.estimate")
      : null;
    if (!estimate || !Array.isArray(estimate.lines) || !estimate.lines.length) {
      throw new KolibriApiError("Смета не содержит редактируемых строк", { status: 502 });
    }
    result = { type: "deterministic_estimate", estimate, calculation };
  } else if (status !== "failed") {
    const responseText = task.result?.type === "verified_provider_response" && typeof task.result.text === "string"
      ? task.result.text
      : "";
    if (!responseText) throw new KolibriApiError("Typed gateway не вернул верифицированный текст результата", { status: 502 });
    result = { type: "verified_provider_response", text: responseText };
  }
  const persistence = task.persistence && typeof task.persistence === "object"
    && typeof task.persistence.estimate_id === "string"
    && Number.isSafeInteger(task.persistence.version)
    && task.persistence.version > 0
    && SHA256.test(String(task.persistence.spec_sha256 || ""))
    && SHA256.test(String(task.persistence.calculation_sha256 || ""))
    ? {
        estimate_id: task.persistence.estimate_id,
        version_id: typeof task.persistence.version_id === "string" ? task.persistence.version_id : "",
        version: task.persistence.version,
        state: task.persistence.state === "saved" ? "saved" : "unknown",
        spec_sha256: String(task.persistence.spec_sha256).toLowerCase(),
        calculation_sha256: String(task.persistence.calculation_sha256).toLowerCase(),
      }
    : null;
  return {
    schema_version: PUBLIC_TASK_SCHEMA,
    intent,
    status,
    execution: {
      status: providerVerified ? "completed" : "failed",
      model: "kolibri",
      provider_verified: providerVerified,
      ...(SHA256.test(String(execution.output_sha256 || "")) ? { output_sha256: String(execution.output_sha256).toLowerCase() } : {}),
      ...(SHA256.test(String(execution.verifier_binding_sha256 || "")) ? { verifier_binding_sha256: String(execution.verifier_binding_sha256).toLowerCase() } : {}),
    },
    result,
    persistence,
    artifacts,
    artifact_delivery: {
      required: requested.length > 0,
      status: requested.length === 0 ? "not_required" : missing.length === 0 ? "materialized" : "not_materialized",
      requested,
      delivered,
      missing,
      count: artifacts.length,
    },
  };
}

export async function sendKolibriRequest({ text, messages = [], workstreamId = "", task = null, executionMode = "fast", metadata = {}, signal }) {
  const requestId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const prompt = nonEmptyText(text, "request.text");
  const conversation = buildConversationMessages(messages, prompt);
  const typedTask = task === null || task === undefined ? null : normalizeTaskForTransport(task);
  const execution_mode = enumValue(executionMode, ["fast", "codex"], "request.execution_mode");
  const idempotencyKey = `shell:${requestId}`;
  await ensurePublicSession();
  const sessionGeneration = publicSessionGeneration;
  const body = {
    model: "kolibri",
    input: conversation,
    stream: true,
    execution_mode,
    idempotency_key: idempotencyKey,
    ...(typedTask ? { task: typedTask } : {}),
    ...((workstreamId || Object.keys(metadata).length) ? {
      metadata: clonePublicValue({
        ...(workstreamId ? { shell_project_ref: String(workstreamId).slice(0, 300) } : {}),
        ...metadata,
      }, "request.metadata"),
    } : {}),
  };
  try {
    let payload;
    try {
      payload = await requestResponsesStream(body, idempotencyKey, signal);
    } catch (error) {
      if (!publicSessionExpired(error)) throw error;
      // A backend restart or normal TTL expiry invalidates only the scoped
      // browser session. Re-issue the HttpOnly cookie and replay the same
      // idempotent Responses request exactly once; never retry provider/auth
      // failures or origin mismatches here.
      await refreshPublicSession(sessionGeneration);
      payload = await requestResponsesStream(body, idempotencyKey, signal);
    }
    const taskEnvelope = typedTask ? normalizeTypedTaskEnvelope(payload?.task, typedTask.intent) : null;
    if (taskEnvelope?.status === "failed") {
      throw new KolibriApiError("Исполнитель не вернул верифицированный результат", {
        status: 502,
        endpoint: API_ENDPOINTS.response,
      });
    }
    const estimateResult = taskEnvelope?.result?.type === "deterministic_estimate" ? taskEnvelope.result : null;
    const estimateText = estimateResult
      ? `Смета «${estimateResult.estimate.title || "Без названия"}» подготовлена: ${estimateResult.estimate.lines.length} позиций, итог рассчитан детерминированно.`
      : "";
    return {
      text: taskEnvelope?.result?.type === "verified_provider_response"
        ? taskEnvelope.result.text || ""
        : estimateText || extractResponseText(payload),
      blocked: payload?.status === "blocked",
      blockedReason: payload?.error?.code || "",
      taskId: payload?.id || "",
      task: taskEnvelope,
      artifacts: taskEnvelope?.artifacts || [],
      endpoint: API_ENDPOINTS.response,
    };
  } catch (error) {
    if (error instanceof KolibriApiError && error.status >= 400 && error.status < 500) throw error;
    if (error instanceof KolibriApiError && error.message) throw error;
    throw new KolibriApiError("Исполнительный контур временно недоступен", {
      status: error?.status || 0,
      endpoint: API_ENDPOINTS.response,
    });
  }
}

export const browserApi = Object.freeze({
  async createSession({ url, workstreamId = "", signal }) {
    const parsed = new URL(url);
    if (!["http:", "https:"].includes(parsed.protocol)) throw new KolibriApiError("Разрешены только HTTP/HTTPS адреса");
    return requestJson(API_ENDPOINTS.browserSessions, {
      method: "POST",
      body: JSON.stringify({ url: parsed.toString(), workstream_id: workstreamId || undefined, sandbox: "isolated" }),
      signal,
    });
  },
});

export const automationApi = Object.freeze({
  validate(draft, signal) {
    return requestJson(API_ENDPOINTS.automationValidate, {
      method: "POST",
      body: JSON.stringify({ ...draft, dry_run: true }),
      signal,
    });
  },
});

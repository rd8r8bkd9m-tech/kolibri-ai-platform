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
  publicCapabilities: ["/v1/capabilities", "/v1/public/capabilities"],
  publicProjects: "/v1/projects",
  status: ["/api/factory/status", "/v1/health", "/api/health"],
  tasks: ["/v1/tasks?limit=250"],
  nodes: ["/v1/nodes?limit=250", "/v1/fleet/nodes", "/api/factory/roster"],
  models: ["/v1/models", "/api/models"],
  capabilities: ["/v1/runtime/product-capabilities"],
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

function publicErrorCode(error) {
  const candidates = [
    error?.payload?.detail?.code,
    error?.payload?.error?.code,
    error?.payload?.code,
    typeof error?.payload?.detail === "string" ? error.payload.detail : "",
  ];
  return String(candidates.find((value) => typeof value === "string" && value) || "").toLowerCase();
}

/** Convert transport and policy errors into a stable message that is safe to
 * render in the public Shell. Raw gateway details stay on the error object for
 * diagnostics and are never echoed into the conversation. */
export function publicErrorMessage(error) {
  if (error?.name === "AbortError") return "Запрос отменён.";
  const status = Number(error?.status) || 0;
  const code = publicErrorCode(error);
  if (code === "origin_not_allowed") {
    return "Этот адрес страницы не разрешён сервером Kolibri. Откройте официальный адрес и повторите запрос.";
  }
  if (code.includes("public_session")) {
    return "Безопасная сессия Kolibri не подтверждена. Обновите страницу и повторите запрос.";
  }
  if (status === 401) {
    return "Сессия Kolibri истекла или не подтверждена. Обновите страницу и повторите запрос.";
  }
  if (status === 403 || /\bforbidden\b|access denied|доступ запрещ[её]н/i.test(String(error?.message || ""))) {
    return "Операция недоступна для текущей публичной сессии.";
  }
  if (status === 429) return "Слишком много запросов. Подождите немного и повторите попытку.";
  if (code === "provider_timeout") {
    return "Исполнитель перестал передавать прогресс. Задача сохранена — продолжите её повторным запуском.";
  }
  if ([
    "provider_capacity_unavailable",
    "provider_service_unavailable",
    "provider_routes_unavailable",
    "provider_routes_exhausted",
  ].includes(code)) {
    return "Все доступные маршруты исполнения сейчас заняты или недоступны. Повторите запрос позже.";
  }
  if (["provider_result_rejected", "verification_failed"].includes(code)) {
    return "Полученный результат не прошёл проверку целостности и не был показан.";
  }
  if (status >= 500) return "Исполнительный контур временно недоступен. Повторите запрос позже.";
  if (status >= 400) return "Запрос не принят сервером Kolibri. Проверьте данные и повторите попытку.";
  const localMessage = typeof error?.message === "string" ? error.message.trim() : "";
  return localMessage || "Не удалось выполнить запрос. Проверьте подключение и повторите попытку.";
}

const WORK_SUMMARY_KINDS = new Set(["plan", "tool", "source", "check", "verdict"]);
const WORK_SUMMARY_STATUSES = new Set(["pending", "running", "passed", "failed", "skipped", "available", "incomplete", "blocked"]);
const WORK_SUMMARY_SECRET_PATTERN = /(?:\bsk-[a-z0-9_-]{8,}|\b(?:authorization|api[_-]?key|password|secret|token)\s*[:=])/i;
const WORK_SUMMARY_SOURCE_SECRET_PATH = /(?:\bsk-[a-z0-9_-]{8,}|\b(?:api[_-]?key|password|secret|token)[=/:_-][^/?#]{4,})/i;
const WORK_SUMMARY_SOURCE_DOMAIN = /^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/i;
const WORK_SUMMARY_PRIVATE_SOURCE_SUFFIXES = [".localhost", ".local", ".internal", ".home.arpa"];

function hasControlCharacters(value) {
  return [...value].some((character) => {
    const code = character.codePointAt(0);
    return code <= 31 || code === 127;
  });
}

function validSourceDate(value) {
  if (value === undefined) return true;
  if (typeof value !== "string" || value.length > 20) return false;
  if (/^\d{4}-Q[1-4]$/.test(value)) return true;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}

function isPublicSourceDomain(domain) {
  if (!WORK_SUMMARY_SOURCE_DOMAIN.test(domain)) return false;
  if (domain === "localhost" || WORK_SUMMARY_PRIVATE_SOURCE_SUFFIXES.some((suffix) => domain.endsWith(suffix))) return false;
  const octets = domain.split(".");
  if (octets.length !== 4 || !octets.every((value) => /^\d{1,3}$/.test(value) && Number(value) <= 255)) return true;
  const [first, second] = octets.map(Number);
  return !(
    first === 0
    || first === 10
    || first === 127
    || first >= 224
    || (first === 100 && second >= 64 && second <= 127)
    || (first === 169 && second === 254)
    || (first === 172 && second >= 16 && second <= 31)
    || (first === 192 && second === 168)
  );
}

function normalizeWorkSources(payload) {
  const encoded = payload?.metadata?.kolibri_work_sources;
  if (encoded === undefined) return [];
  if (typeof encoded !== "string" || encoded.length > 512) return null;
  let parsed;
  try {
    parsed = JSON.parse(encoded);
  } catch {
    return null;
  }
  if (parsed?.v !== 1 || !Array.isArray(parsed?.sources) || parsed.sources.length > 4) return null;
  const sources = [];
  for (const source of parsed.sources) {
    if (!source || typeof source !== "object" || Array.isArray(source)) return null;
    if (typeof source.url !== "string" || source.url.length > 280 || typeof source.domain !== "string") return null;
    let url;
    try {
      url = new URL(source.url);
    } catch {
      return null;
    }
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) return null;
    const domain = source.domain.toLowerCase().replace(/\.$/, "");
    let decodedPath;
    try {
      decodedPath = decodeURIComponent(url.pathname);
    } catch {
      return null;
    }
    if (
      !isPublicSourceDomain(domain)
      || url.hostname.toLowerCase() !== domain
      || WORK_SUMMARY_SOURCE_SECRET_PATH.test(decodedPath)
    ) return null;
    if (!validSourceDate(source.price_level_date) || !validSourceDate(source.captured_at)) return null;
    sources.push({
      url: url.toString(),
      domain,
      ...(source.price_level_date ? { price_level_date: source.price_level_date } : {}),
      ...(source.captured_at ? { captured_at: source.captured_at } : {}),
    });
  }
  return sources;
}

export function normalizeWorkSummary(payload) {
  const encoded = payload?.metadata?.kolibri_work_summary;
  if (typeof encoded !== "string" || encoded.length > 512) return null;
  let parsed;
  try {
    parsed = JSON.parse(encoded);
  } catch {
    return null;
  }
  if (parsed?.v !== 1 || parsed?.mode !== "summary_only" || !Array.isArray(parsed?.items)) return null;
  const sources = normalizeWorkSources(payload);
  if (sources === null) return null;
  const items = [];
  for (const item of parsed.items.slice(0, 5)) {
    if (!WORK_SUMMARY_KINDS.has(item?.kind) || !WORK_SUMMARY_STATUSES.has(item?.status)) return null;
    const detail = typeof item.detail === "string" ? item.detail.trim() : "";
    if (detail.length > 160 || hasControlCharacters(detail) || WORK_SUMMARY_SECRET_PATTERN.test(detail)) return null;
    items.push({
      kind: item.kind,
      status: item.status,
      detail,
      ...(item.kind === "source" && sources.length ? { sources } : {}),
    });
  }
  return items.length ? {
    schema_version: "kolibri.work-summary.v1",
    mode: "summary_only",
    raw_reasoning_exposed: false,
    items,
  } : null;
}

function normalizeWorkSummaryEvent(value) {
  if (
    value?.schema_version !== "kolibri.work-summary.v1"
    || value?.mode !== "summary_only"
    || value?.raw_reasoning_exposed !== false
    || !Array.isArray(value?.items)
  ) return null;
  const sourceItem = value.items.find((item) => item?.kind === "source");
  return normalizeWorkSummary({
    metadata: {
      kolibri_work_summary: JSON.stringify({
        v: 1,
        mode: "summary_only",
        items: value.items.map((item) => ({
          kind: item?.kind,
          status: item?.status,
          detail: item?.detail,
        })),
      }),
      ...(Array.isArray(sourceItem?.sources) && sourceItem.sources.length ? {
        kolibri_work_sources: JSON.stringify({ v: 1, sources: sourceItem.sources }),
      } : {}),
    },
  });
}

function reasoningSummaryProgress(value) {
  if (typeof value !== "string" || value.length > 6_000 || hasControlCharacters(value) || WORK_SUMMARY_SECRET_PATTERN.test(value)) return null;
  const labels = [
    ["План: ", "plan"],
    ["Инструменты: ", "tool"],
    ["Источники: ", "source"],
    ["Проверка: ", "check"],
    ["Итог: ", "verdict"],
  ];
  const match = labels.find(([label]) => value.startsWith(label));
  if (match) {
    const detail = value.slice(match[0].length).trim();
    return detail ? { activeKind: match[1], detail } : null;
  }
  const detail = value.trim();
  return detail ? { detail } : null;
}

const RESPONSE_STAGE_PROGRESS = Object.freeze({
  routing: { activeKind: "plan", detail: "Подбираю подходящий маршрут исполнения" },
  fallback: { activeKind: "plan", detail: "Переключаюсь на резервного исполнителя" },
  queued: { activeKind: "tool", detail: "Задача принята фабрикой" },
  leased: { activeKind: "tool", detail: "Исполнитель получил задачу" },
  running: { activeKind: "plan", detail: "Исполнитель работает над ответом" },
  verifying: { activeKind: "check", detail: "Проверяю результат" },
});

async function requestJson(path, options = {}) {
  const requestHeaders = options.body instanceof FormData
    ? options.headers
    : { "Content-Type": "application/json", ...options.headers };
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "same-origin",
    ...options,
    headers: requestHeaders,
  });
  const contentType = String(response.headers.get("content-type") || "");
  const mediaType = contentType.split(";", 1)[0].trim().toLowerCase();
  if (mediaType !== "application/json") {
    throw new KolibriApiError("API вернул ответ не в формате JSON", {
      status: response.ok ? 502 : response.status,
      endpoint: path,
      payload: {
        code: "api_response_content_type_invalid",
        upstream_status: response.status,
        content_type: contentType.slice(0, 160),
      },
    });
  }
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new KolibriApiError("API вернул повреждённый JSON", {
      status: response.ok ? 502 : response.status,
      endpoint: path,
      payload: {
        code: "api_response_json_invalid",
        upstream_status: response.status,
      },
    });
  }
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

function publicProjectSessionMismatch(error) {
  if (!(error instanceof KolibriApiError)) return false;
  const code = publicErrorCode(error);
  if (error.status === 404) {
    return code === "project_not_found" || code === "project_not_found_in_session";
  }
  if (error.status !== 403) return false;
  return new Set([
    "project_not_found_in_session",
    "public_session_project_not_owned",
    "public_session_project_forbidden",
  ]).has(code);
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

function publicSessionNotPersisted() {
  return new KolibriApiError("Не удалось закрепить безопасную сессию. Повторите сообщение.", {
    status: 401,
    endpoint: API_ENDPOINTS.publicSession,
    payload: { code: "public_session_cookie_not_persisted" },
  });
}

async function createPublicSession() {
  assertPublicSession(await requestJson(API_ENDPOINTS.publicSession, {
    method: "POST",
    body: JSON.stringify({}),
    cache: "no-store",
  }));
  try {
    // A successful POST proves only that the server issued a session. Verify
    // that the browser retained the HttpOnly cookie before dispatching work;
    // legacy duplicate-path cookies can otherwise shadow the fresh value.
    return assertPublicSession(await requestJson(API_ENDPOINTS.publicSession, {
      cache: "no-store",
    }));
  } catch (error) {
    if (publicSessionExpired(error)) throw publicSessionNotPersisted();
    throw error;
  }
}

export async function ensurePublicSession() {
  if (publicSessionRefreshPromise) return publicSessionRefreshPromise;
  if (publicSessionPromise) return publicSessionPromise;
  const sessionPromise = (async () => {
    try {
      // Session discovery is shared by every in-flight Shell request.  A
      // caller-specific AbortSignal must not cancel that shared handshake and
      // poison unrelated requests; the signal remains scoped to /responses.
      const current = await requestJson(API_ENDPOINTS.publicSession, { cache: "no-store" });
      if (current.payload?.object === "public.session" && current.payload?.active !== false) return current.payload;
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

async function consumeResponsesSse(response, onWorkSummary, onTextDelta) {
  let buffer = "";
  let streamedText = "";
  let completed = null;
  let latestWorkSummary = null;
  let streamedReasoningSummary = "";

  const notifyWorkSummary = (workSummary, progress = {}) => {
    if (!workSummary) return;
    latestWorkSummary = workSummary;
    if (typeof onWorkSummary !== "function") return;
    try {
      onWorkSummary(workSummary, progress);
    } catch {
      // Rendering progress is observational and must never abort execution.
    }
  };

  const notifyTextDelta = (delta) => {
    if (typeof onTextDelta !== "function") return;
    try {
      onTextDelta(delta, streamedText);
    } catch {
      // Incremental rendering is observational and must never abort execution.
    }
  };

  const acceptBlock = (block) => {
    const parsed = parseSseBlock(block);
    if (!parsed) return;
    const payload = parsed.data;
    const type = payload?.type || parsed.event;
    const responsePayload = payload?.response;
    if (responsePayload) {
      notifyWorkSummary(normalizeWorkSummary(responsePayload));
    }
    if (type === "response.kolibri_work_summary.updated") {
      const workSummary = normalizeWorkSummaryEvent(payload.summary);
      const activeKind = WORK_SUMMARY_KINDS.has(payload.active_kind) ? payload.active_kind : "";
      notifyWorkSummary(workSummary, { activeKind });
    } else if (type === "response.status.updated") {
      const progress = RESPONSE_STAGE_PROGRESS[payload.stage];
      if (progress && latestWorkSummary) notifyWorkSummary(latestWorkSummary, progress);
    } else if (type === "response.tool.started") {
      if (latestWorkSummary) notifyWorkSummary(latestWorkSummary, {
        activeKind: "tool",
        detail: "Использую подключённый инструмент",
      });
    } else if (type === "response.tool.completed") {
      if (latestWorkSummary) notifyWorkSummary(latestWorkSummary, {
        activeKind: "check",
        detail: "Инструмент завершил работу, проверяю результат",
      });
    } else if (type === "response.reasoning_summary_text.delta") {
      if (typeof payload.delta === "string") streamedReasoningSummary += payload.delta;
      const progress = reasoningSummaryProgress(streamedReasoningSummary);
      if (progress && latestWorkSummary) notifyWorkSummary(latestWorkSummary, progress);
    }
    if (type === "response.output_text.delta" && typeof payload.delta === "string") {
      streamedText += payload.delta;
      notifyTextDelta(payload.delta);
    } else if (type === "response.completed" && payload.response) {
      completed = payload.response;
    } else if (type === "response.failed" || type === "error") {
      const failed = payload.response || payload;
      const serverError = failed?.error && typeof failed.error === "object" ? failed.error : {};
      const code = typeof serverError.code === "string" && serverError.code
        ? serverError.code
        : "response_failed";
      throw new KolibriApiError(
        typeof serverError.message === "string" && serverError.message
          ? serverError.message
          : "Маршруты исполнения завершились без подтверждённого результата",
        {
          status: 503,
          endpoint: API_ENDPOINTS.response,
          payload: {
            code,
            error: {
              code,
              ...(typeof serverError.type === "string" ? { type: serverError.type } : {}),
              ...(typeof serverError.retryable === "boolean" ? { retryable: serverError.retryable } : {}),
              ...(serverError.attempt_summary && typeof serverError.attempt_summary === "object"
                ? { attempt_summary: serverError.attempt_summary }
                : {}),
            },
          },
        },
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

async function requestResponsesStream(body, idempotencyKey, signal, onWorkSummary, onTextDelta) {
  const response = await fetch(`${API_BASE}${API_ENDPOINTS.response}`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify(body),
    cache: "no-store",
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
  return consumeResponsesSse(response, onWorkSummary, onTextDelta);
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

export async function loadPublicCapabilities(signal) {
  const response = await firstAvailable(API_ENDPOINTS.publicCapabilities, {
    signal,
    cache: "no-store",
  });
  return normalizeCapabilities(response.payload);
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
    .filter((message) => (
      message
      && CONVERSATION_ROLES.has(message.role)
      && !["running", "failed"].includes(message.status)
      && message.recoverable !== true
      && message.excludeFromContext !== true
    ))
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
const PUBLIC_TASK_INTENTS = Object.freeze(["estimate", "document", "image", "site", "app"]);
const ESTIMATE_FALLBACK_ENGINE = "kolibri.estimate-readiness-gate.v1";
const ESTIMATE_FALLBACK_PROOF_SCHEMA = "kolibri.estimate-readiness-proof.v1";
const ESTIMATE_READINESS_SCHEMA = "kolibri.estimate-readiness.v1";
const ESTIMATE_READINESS_EDITOR_SCHEMA = "kolibri.estimate-input-editor.v1";
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
  image: new Set(["intent", "brief", "requested_artifacts"]),
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
  normativeBasis = null,
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
    const provenanceKeys = new Set([
      "source", "source_ref", "captured_at", "applicable_region",
      "source_url", "price_level_date", "basis_ref", "quantity_source",
      "quantity_source_ref", "quantity_source_url", "assumptions", "validation_status",
    ]);
    for (const key of Object.keys(provenance)) if (!provenanceKeys.has(key)) throw new KolibriApiError(`estimate.lines[${index}].provenance.${key}: неизвестное поле`);
    provenance.source = enumValue(provenance.source || "manual", ["manual", "assumption", "normative", "catalog", "contract", "supplier", "measurement"], `estimate.lines[${index}].provenance.source`);
    if (provenance.quantity_source !== undefined) {
      provenance.quantity_source = enumValue(provenance.quantity_source, ["project", "measurement", "manual"], `estimate.lines[${index}].provenance.quantity_source`);
    }
    provenance.validation_status = enumValue(provenance.validation_status || "unverified", ["unverified", "verified"], `estimate.lines[${index}].provenance.validation_status`);
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
  let normalizedBasis = null;
  if (normativeBasis !== null && normativeBasis !== undefined) {
    const basis = clonePublicValue(normativeBasis, "estimate.normative_basis");
    const allowed = new Set([
      "calculation_method", "normative_basis_ref", "normative_edition",
      "price_level_date", "region", "index_document_refs", "tax_scope_ref",
      "contract_scope_ref", "source_urls", "input_document_refs", "validation_status",
    ]);
    for (const key of Object.keys(basis)) if (!allowed.has(key)) throw new KolibriApiError(`estimate.normative_basis.${key}: неизвестное поле`);
    normalizedBasis = {
      calculation_method: enumValue(basis.calculation_method, ["resource-index", "resource", "base-index", "contract", "commercial"], "estimate.normative_basis.calculation_method"),
      normative_basis_ref: nonEmptyText(basis.normative_basis_ref, "estimate.normative_basis.normative_basis_ref", 1_000),
      normative_edition: nonEmptyText(basis.normative_edition, "estimate.normative_basis.normative_edition", 300),
      price_level_date: nonEmptyText(basis.price_level_date, "estimate.normative_basis.price_level_date", 80),
      region: nonEmptyText(basis.region, "estimate.normative_basis.region", 300),
      index_document_refs: clonePublicValue(basis.index_document_refs || [], "estimate.normative_basis.index_document_refs"),
      tax_scope_ref: nonEmptyText(basis.tax_scope_ref, "estimate.normative_basis.tax_scope_ref", 1_000),
      contract_scope_ref: nonEmptyText(basis.contract_scope_ref, "estimate.normative_basis.contract_scope_ref", 1_000),
      source_urls: clonePublicValue(basis.source_urls || [], "estimate.normative_basis.source_urls"),
      input_document_refs: clonePublicValue(basis.input_document_refs || [], "estimate.normative_basis.input_document_refs"),
      validation_status: enumValue(basis.validation_status || "unverified", ["unverified", "verified"], "estimate.normative_basis.validation_status"),
    };
  }
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
      ...(normalizedBasis ? { normative_basis: normalizedBasis } : {}),
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

export async function submitEstimateFeedback({
  estimateId,
  baseVersion,
  action,
  reason = "",
  corrections = {},
} = {}) {
  const id = nonEmptyText(estimateId, "estimate.feedback.estimate_id", 200);
  const reviewAction = enumValue(action, ["accept", "reject", "correct"], "estimate.feedback.action");
  const version = integerInRange(baseVersion, 1, Number.MAX_SAFE_INTEGER, "estimate.feedback.base_version");
  if (["reject", "correct"].includes(reviewAction) && !String(reason || "").trim() && !Object.keys(corrections || {}).length) {
    throw new KolibriApiError("estimate.feedback: укажите причину или исправления");
  }
  await ensurePublicSession();
  const requestId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const result = await requestJson(`/v1/public/estimates/${encodeURIComponent(id)}/feedback`, {
    method: "POST",
    body: JSON.stringify({
      action: reviewAction,
      base_version: version,
      reason: String(reason || "").trim() || null,
      corrections: clonePublicValue(corrections || {}, "estimate.feedback.corrections"),
      idempotency_key: `estimate-feedback:${requestId}`,
    }),
    cache: "no-store",
  });
  return result.payload;
}

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

export function buildImageTask({ brief, ...routingOrUnknown } = {}) {
  assertNoRoutingSelection(routingOrUnknown, "image");
  if (Object.keys(routingOrUnknown).length) throw new KolibriApiError(`image.${Object.keys(routingOrUnknown)[0]}: неизвестное поле`);
  return {
    intent: "image",
    brief: nonEmptyText(brief, "image.brief", 20_000),
    requested_artifacts: ["image"],
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
  if (artifact.document_role === "estimate_input_checklist") result.document_role = artifact.document_role;
  if (SHA256.test(String(artifact.readiness_sha256 || ""))) result.readiness_sha256 = String(artifact.readiness_sha256).toLowerCase();
  if (SHA256.test(String(artifact.task_binding_sha256 || ""))) result.task_binding_sha256 = String(artifact.task_binding_sha256).toLowerCase();
  for (const key of ["kind", "name", "locator", "origin", "media_type"]) {
    if (typeof artifact[key] === "string" && artifact[key]) result[key] = artifact[key];
  }
  return result;
}


function containsForbiddenEstimateMoney(value) {
  const forbidden = new Set([
    "unit_price_minor", "line_total_minor", "totals", "subtotal_minor",
    "grand_total_minor", "tax_minor", "overhead_minor", "amount_minor",
  ]);
  if (Array.isArray(value)) return value.some(containsForbiddenEstimateMoney);
  if (!value || typeof value !== "object") return false;
  return Object.entries(value).some(([key, child]) => forbidden.has(String(key).toLowerCase()) || containsForbiddenEstimateMoney(child));
}

function normalizeEstimatePriceResearch(value, estimate, estimateStatus) {
  if (value === undefined || value === null) return null;
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new KolibriApiError("Исследование текущих цен имеет неверный формат", { status: 502 });
  }
  const expectedLines = Array.isArray(estimate?.lines) ? estimate.lines : [];
  const rawLines = Array.isArray(value.lines) ? value.lines : [];
  const controlledSearch = value.status === "source_bound_preliminary"
    && value.source_validation === "controlled_search_snippet_binding";
  const providerAsserted = value.status === "provider_asserted_unverified"
    && value.source_validation === "native_search_event_with_provider_asserted_sources";
  const nativeBinding = value.native_tool_binding && typeof value.native_tool_binding === "object"
    && !Array.isArray(value.native_tool_binding)
    ? value.native_tool_binding
    : null;
  const nativeCallIds = Array.isArray(nativeBinding?.tool_call_ids)
    ? nativeBinding.tool_call_ids
    : [];
  const validNativeBinding = providerAsserted
    && nativeBinding?.schema_version === "kolibri.native-web-search-binding.v1"
    && nativeBinding.tool_id === "tool:web_search"
    && nativeBinding.source_claim === "provider_asserted_unverified"
    && SHA256.test(String(nativeBinding.verifier_binding_sha256 || ""))
    && nativeCallIds.length > 0
    && nativeCallIds.length <= 32
    && new Set(nativeCallIds).size === nativeCallIds.length
    && nativeCallIds.every((callId) => (
      typeof callId === "string"
      && /^[A-Za-z0-9._:-]{1,200}$/.test(callId)
    ));
  if (
    value.schema_version !== "kolibri.estimate-price-research.v1"
    || estimateStatus !== "preliminary"
    || (!controlledSearch && !validNativeBinding)
    || value.region !== estimate.region
    || value.minor_unit !== estimate.minor_unit
    || value.selection_rule !== "range_midpoint_round_half_up"
    || value.independent_normative_verification !== false
    || !SHA256.test(String(value.binding_sha256 || ""))
    || rawLines.length !== expectedLines.length
  ) {
    throw new KolibriApiError("Исследование текущих цен не прошло проверку контракта", { status: 502 });
  }
  const estimateById = new Map(expectedLines.map((line) => [line?.id, line]));
  const seen = new Set();
  const lines = rawLines.map((raw) => {
    const lineId = typeof raw?.line_id === "string" ? raw.line_id : "";
    const estimateLine = estimateById.get(lineId);
    const priceMin = raw?.price_min_minor;
    const priceMax = raw?.price_max_minor;
    const selected = raw?.selected_unit_price_minor;
    const midpoint = Number.isSafeInteger(priceMin) && Number.isSafeInteger(priceMax)
      ? Math.floor((priceMin + priceMax + 1) / 2)
      : -1;
    let source;
    try {
      source = new URL(raw?.source_url);
    } catch {
      source = null;
    }
    const sourceHost = typeof raw?.source_host === "string"
      ? raw.source_host.toLowerCase().replace(/\.$/, "")
      : "";
    const retrievedText = typeof raw?.source_retrieved_at === "string"
      ? raw.source_retrieved_at
      : "";
    const retrieved = retrievedText
      ? Date.parse(retrievedText)
      : Number.NaN;
    const observedOn = typeof raw?.observed_on === "string" ? raw.observed_on : "";
    const observedDate = /^\d{4}-\d{2}-\d{2}$/.test(observedOn)
      ? Date.parse(`${observedOn}T00:00:00Z`)
      : Number.NaN;
    const validProviderAssertion = !providerAsserted || (
      raw.provider_asserted === true
      && raw.independently_citation_bound === false
      && estimateLine?.provenance?.validation_status === "unverified"
      && source?.protocol === "https:"
      && Number.isFinite(observedDate)
      && new Date(observedDate).toISOString().slice(0, 10) === observedOn
      && retrievedText.slice(0, 10) === observedOn
    );
    if (
      !estimateLine
      || seen.has(lineId)
      || !Number.isSafeInteger(priceMin) || priceMin < 0
      || !Number.isSafeInteger(priceMax) || priceMax < priceMin
      || !Number.isSafeInteger(selected) || selected !== midpoint
      || estimateLine.unit_price_minor !== selected
      || raw.selection_rule !== "range_midpoint_round_half_up"
      || !source || !["http:", "https:"].includes(source.protocol)
      || source.username || source.password
      || !isPublicSourceDomain(sourceHost) || source.hostname.toLowerCase() !== sourceHost
      || raw.source_url !== estimateLine.provenance?.source_url
      || typeof raw.source_quote !== "string" || !raw.source_quote.trim() || raw.source_quote.length > 1_000
      || !SHA256.test(String(raw.source_content_sha256 || ""))
      || !Number.isFinite(retrieved)
      || typeof raw.source_title !== "string" || !raw.source_title.trim() || raw.source_title.length > 500
      || !validProviderAssertion
    ) {
      throw new KolibriApiError("Строка исследования цен не привязана к позиции сметы", { status: 502 });
    }
    seen.add(lineId);
    return {
      line_id: lineId,
      price_min_minor: priceMin,
      price_max_minor: priceMax,
      selection_rule: "range_midpoint_round_half_up",
      selected_unit_price_minor: selected,
      source_url: source.toString(),
      source_quote: raw.source_quote.trim(),
      source_content_sha256: String(raw.source_content_sha256).toLowerCase(),
      source_retrieved_at: raw.source_retrieved_at,
      source_title: raw.source_title.trim(),
      source_host: sourceHost,
      ...(providerAsserted ? {
        provider_asserted: true,
        independently_citation_bound: false,
        observed_on: observedOn,
      } : {}),
    };
  });
  return {
    schema_version: "kolibri.estimate-price-research.v1",
    status: value.status,
    region: value.region,
    minor_unit: value.minor_unit,
    selection_rule: "range_midpoint_round_half_up",
    source_validation: value.source_validation,
    independent_normative_verification: false,
    lines,
    ...(providerAsserted ? {
      native_tool_binding: {
        schema_version: "kolibri.native-web-search-binding.v1",
        tool_id: "tool:web_search",
        tool_call_ids: [...nativeCallIds],
        verifier_binding_sha256: String(nativeBinding.verifier_binding_sha256).toLowerCase(),
        source_claim: "provider_asserted_unverified",
      },
    } : {}),
    binding_sha256: String(value.binding_sha256).toLowerCase(),
  };
}

export function normalizeTypedTaskEnvelope(task, expectedIntent = "") {
  if (!task || typeof task !== "object" || task.schema_version !== PUBLIC_TASK_SCHEMA) {
    throw new KolibriApiError("Typed gateway не вернул контракт Kolibri public-task.v1", { status: 502 });
  }
  const intent = enumValue(task.intent, PUBLIC_TASK_INTENTS, "task.intent");
  if (expectedIntent && intent !== expectedIntent) throw new KolibriApiError("Typed gateway вернул результат другой задачи", { status: 502 });
  const execution = task.execution && typeof task.execution === "object" ? task.execution : {};
  const providerVerified = execution.provider_verified === true
    && execution.status === "completed"
    && execution.model === "kolibri"
    && SHA256.test(String(execution.output_sha256 || ""))
    && SHA256.test(String(execution.verifier_binding_sha256 || ""));
  const generation = task.result?.generation && typeof task.result.generation === "object" ? task.result.generation : {};
  const providerBinding = generation.provider_binding && typeof generation.provider_binding === "object" ? generation.provider_binding : null;
  const readinessEngineVerified = intent === "estimate"
    && execution.engine_verified === true
    && execution.status === "completed"
    && execution.model === "kolibri"
    && execution.engine === ESTIMATE_FALLBACK_ENGINE
    && generation.schema_version === ESTIMATE_FALLBACK_PROOF_SCHEMA
    && generation.engine === ESTIMATE_FALLBACK_ENGINE
    && generation.mode === "needs_input"
    && generation.source_mode === (providerVerified ? "provider_reviewed" : "local_gate")
    && execution.provider_status === (providerVerified ? "completed" : "failed")
    && /^[a-z0-9_]{1,80}$/.test(String(generation.fallback_reason || ""))
    && execution.fallback_reason === generation.fallback_reason
    && SHA256.test(String(execution.engine_binding_sha256 || ""))
    && String(execution.engine_binding_sha256).toLowerCase() === String(generation.binding_sha256 || "").toLowerCase()
    && SHA256.test(String(generation.input_facts_sha256 || ""))
    && SHA256.test(String(generation.readiness_sha256 || ""))
    && generation.input_facts && typeof generation.input_facts === "object"
    && (providerVerified
      ? providerBinding
        && SHA256.test(String(providerBinding.output_sha256 || ""))
        && SHA256.test(String(providerBinding.verifier_binding_sha256 || ""))
        && String(providerBinding.output_sha256).toLowerCase() === String(execution.output_sha256).toLowerCase()
        && String(providerBinding.verifier_binding_sha256).toLowerCase() === String(execution.verifier_binding_sha256).toLowerCase()
      : execution.provider_verified === false && providerBinding === null);
  const executionVerified = providerVerified || readinessEngineVerified;
  const delivery = task.artifact_delivery && typeof task.artifact_delivery === "object" ? task.artifact_delivery : {};
  const requested = Array.isArray(delivery.requested) ? [...new Set(delivery.requested.filter((item) => typeof item === "string" && item))] : [];
  const reportedDelivered = new Set(Array.isArray(delivery.delivered) ? delivery.delivered.filter((item) => requested.includes(item)) : []);
  const artifacts = executionVerified && Array.isArray(task.artifacts)
    ? task.artifacts.map((artifact) => safeArtifact(artifact, reportedDelivered)).filter(Boolean)
    : [];
  const delivered = [...new Set(artifacts.map((artifact) => artifact.deliverable_type))].sort();
  const missing = requested.filter((item) => !delivered.includes(item));
  const serverStatus = ["completed", "incomplete", "failed"].includes(task.status) ? task.status : "failed";
  const status = !executionVerified || serverStatus === "failed"
    ? "failed"
    : serverStatus === "completed" && missing.length === 0
      ? "completed"
      : "incomplete";
  let result = null;
  if (status !== "failed" && intent === "estimate") {
    if (task.result?.type === "estimate_readiness") {
      const readiness = task.result.readiness && typeof task.result.readiness === "object"
        ? clonePublicValue(task.result.readiness, "task.result.readiness")
        : null;
      const validReadiness = readinessEngineVerified
        && readiness?.schema_version === ESTIMATE_READINESS_SCHEMA
        && readiness.status === "needs_input"
        && readiness.monetary_status === "not_calculated"
        && readiness.normative_verified === false
        && readiness.editor?.schema_version === ESTIMATE_READINESS_EDITOR_SCHEMA
        && readiness.editor?.state === "needs_input"
        && Array.isArray(readiness.editor?.fields)
        && readiness.editor.fields.length > 0
        && Array.isArray(readiness.required_inputs)
        && readiness.required_inputs.length > 0
        && readiness.required_inputs.every((item) => item && item.status === "missing")
        && Array.isArray(readiness.draft_sections)
        && readiness.draft_sections.every((section) => section && Array.isArray(section.items) && section.items.length === 0)
        && !containsForbiddenEstimateMoney(readiness);
      if (!validReadiness) {
        throw new KolibriApiError("Проверка готовности сметы не подтверждена", { status: 502 });
      }
      result = {
        type: "estimate_readiness",
        readiness,
        generation: clonePublicValue(generation, "task.result.generation"),
      };
    } else {
      const calculation = task.result?.type === "deterministic_estimate"
        ? clonePublicValue(task.result.calculation, "task.result.calculation")
        : null;
      if (!calculation || calculation.money_authority !== "deterministic_calculator" || calculation.llm_calculates_money !== false) {
        throw new KolibriApiError("Смета не подтверждена детерминированным расчётным контуром", { status: 502 });
      }
      const estimate = task.result?.estimate && typeof task.result.estimate === "object"
        ? clonePublicValue(task.result.estimate, "task.result.estimate")
        : null;
      const verification = task.result?.verification && typeof task.result.verification === "object"
        ? clonePublicValue(task.result.verification, "task.result.verification")
        : null;
      if (!estimate || !Array.isArray(estimate.lines) || !estimate.lines.length) {
        throw new KolibriApiError("Смета не содержит редактируемых строк", { status: 502 });
      }
      const estimateStatus = enumValue(task.result?.status, ["preliminary", "verified"], "task.result.status");
      const validVerification = verification
        && verification.status === estimateStatus
        && verification.monetary_status === "calculated"
        && SHA256.test(String(verification.binding_sha256 || ""))
        && (estimateStatus === "preliminary"
          ? verification.normative_verified === false && verification.commercial_verified === false
          : verification.normative_verified === true || verification.commercial_verified === true);
      if (!validVerification) {
        throw new KolibriApiError("Статус источников сметы не прошёл проверку контракта", { status: 502 });
      }
      const priceResearch = normalizeEstimatePriceResearch(
        task.result?.price_research,
        estimate,
        estimateStatus,
      );
      result = {
        type: "deterministic_estimate",
        status: estimateStatus,
        estimate,
        calculation,
        verification,
        ...(priceResearch ? { price_research: priceResearch } : {}),
      };
    }
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
      status: executionVerified ? "completed" : "failed",
      model: "kolibri",
      provider_verified: providerVerified,
      ...(readinessEngineVerified ? {
        engine_verified: true,
        engine: ESTIMATE_FALLBACK_ENGINE,
        engine_binding_sha256: String(execution.engine_binding_sha256).toLowerCase(),
        provider_status: providerVerified ? "completed" : "failed",
        fallback_reason: String(execution.fallback_reason),
      } : {}),
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

export async function sendKolibriRequest({ text, messages = [], workstreamId = "", projectId = "", task = null, executionMode = "fast", metadata = {}, signal, onWorkSummary, onTextDelta, reconcileProjectId = null }) {
  const requestId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const prompt = nonEmptyText(text, "request.text");
  const conversation = buildConversationMessages(messages, prompt);
  const typedTask = task === null || task === undefined ? null : normalizeTaskForTransport(task);
  const execution_mode = enumValue(executionMode, ["fast", "codex"], "request.execution_mode");
  let project_id = projectId ? nonEmptyText(projectId, "request.project_id", 200) : "";
  if (project_id && !/^project_ephemeral_[A-Za-z0-9._:-]+$/.test(project_id)) {
    throw new KolibriApiError("request.project_id: недопустимый идентификатор проекта");
  }
  const idempotencyKey = `shell:${requestId}`;
  await ensurePublicSession();
  const sessionGeneration = publicSessionGeneration;
  const baseBody = {
    model: "kolibri",
    input: conversation,
    stream: true,
    background: true,
    reasoning: { effort: execution_mode === "codex" ? "high" : "medium", summary: "auto" },
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
    let sessionRefreshUsed = false;
    let projectReconciliationUsed = false;
    const reconcileOwnedProject = async (error) => {
      if (!project_id || typeof reconcileProjectId !== "function") throw error;
      projectReconciliationUsed = true;
      const reboundId = nonEmptyText(await reconcileProjectId({
        failedProjectId: project_id,
        error,
        signal,
      }), "request.reconciled_project_id", 200);
      if (!/^project_ephemeral_[A-Za-z0-9._:-]+$/.test(reboundId)) {
        throw new KolibriApiError("request.reconciled_project_id: недопустимый идентификатор проекта");
      }
      project_id = reboundId;
    };

    // There are only two repair transitions: one public-session refresh and
    // one project reconciliation. Both replay the original idempotency key;
    // no provider/auth/validation error enters this loop and it cannot spin.
    while (true) {
      const body = { ...baseBody, ...(project_id ? { project_id } : {}) };
      try {
        payload = await requestResponsesStream(body, idempotencyKey, signal, onWorkSummary, onTextDelta);
        break;
      } catch (error) {
        if (publicSessionExpired(error) && !sessionRefreshUsed) {
          sessionRefreshUsed = true;
          await refreshPublicSession(sessionGeneration);
          if (project_id && typeof reconcileProjectId === "function" && !projectReconciliationUsed) {
            await reconcileOwnedProject(error);
          }
          continue;
        }
        if (publicSessionExpired(error)) {
          publicSessionPromise = null;
          throw publicSessionNotPersisted();
        }
        if (publicProjectSessionMismatch(error) && !projectReconciliationUsed) {
          await reconcileOwnedProject(error);
          continue;
        }
        throw error;
      }
    }
    const taskEnvelope = typedTask ? normalizeTypedTaskEnvelope(payload?.task, typedTask.intent) : null;
    if (taskEnvelope?.status === "failed") {
      throw new KolibriApiError("Исполнитель не вернул верифицированный результат", {
        status: 502,
        endpoint: API_ENDPOINTS.response,
      });
    }
    const estimateResult = taskEnvelope?.result?.type === "deterministic_estimate" ? taskEnvelope.result : null;
    const readinessResult = taskEnvelope?.result?.type === "estimate_readiness" ? taskEnvelope.result : null;
    const estimateText = estimateResult
      ? `Смета «${estimateResult.estimate.title || "Без названия"}» подготовлена: ${estimateResult.estimate.lines.length} позиций, итог рассчитан детерминированно.`
      : "";
    const readinessText = readinessResult
      ? "Для правдивой сметы нужны исходные документы. Денежный итог не рассчитан; заполните редактор исходных данных."
      : "";
    return {
      text: taskEnvelope?.result?.type === "verified_provider_response"
        ? taskEnvelope.result.text || ""
        : readinessText || estimateText || extractResponseText(payload),
      blocked: payload?.status === "blocked",
      blockedReason: payload?.error?.code || "",
      taskId: payload?.id || "",
      task: taskEnvelope,
      artifacts: taskEnvelope?.artifacts || [],
      workSummary: normalizeWorkSummary(payload),
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

const PUBLIC_PROJECT_ID = /^project_ephemeral_[A-Za-z0-9._:-]+$/;
const PUBLIC_MESSAGE_ID = /^message_[A-Za-z0-9._:-]+$/;
const PUBLIC_MESSAGE_ROLES = ["user", "assistant"];
const PUBLIC_MESSAGE_STATUSES = ["pending", "running", "completed", "failed", "incomplete", "cancelled"];

function publicRecordId(value, pattern, label) {
  const id = nonEmptyText(value, label, 200);
  if (!pattern.test(id)) throw new KolibriApiError(`${label}: недопустимый идентификатор`);
  return id;
}

function publicMutationKey(scope, stableKey = "") {
  const key = String(stableKey || globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`);
  return `${scope}:${key}`.slice(0, 240);
}

async function publicSessionJson(path, options = {}) {
  await ensurePublicSession();
  const observedGeneration = publicSessionGeneration;
  try {
    return (await requestJson(path, options)).payload;
  } catch (error) {
    if (!publicSessionExpired(error)) throw error;
    await refreshPublicSession(observedGeneration);
    try {
      return (await requestJson(path, options)).payload;
    } catch (retryError) {
      if (!publicSessionExpired(retryError)) throw retryError;
      publicSessionPromise = null;
      throw publicSessionNotPersisted();
    }
  }
}

function publicMutationOptions(method, body, key, signal) {
  return {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    signal,
    headers: { "Idempotency-Key": key },
  };
}

/** Canonical session-scoped project/message CRUD. No owner token or durable
 * authority crosses this public browser boundary. */
export const publicProjectsApi = Object.freeze({
  async list(signal) {
    const payload = await publicSessionJson(API_ENDPOINTS.publicProjects, { cache: "no-store", signal });
    return Array.isArray(payload?.data) ? payload.data : [];
  },
  get(projectId, signal) {
    const id = publicRecordId(projectId, PUBLIC_PROJECT_ID, "project.id");
    return publicSessionJson(`${API_ENDPOINTS.publicProjects}/${encodeURIComponent(id)}`, {
      cache: "no-store",
      signal,
    });
  },
  async create({ title, metadata = {}, idempotencyKey = "" }, signal) {
    return publicSessionJson(API_ENDPOINTS.publicProjects, publicMutationOptions("POST", {
      title: nonEmptyText(title, "project.title", 200),
      metadata: clonePublicValue(metadata, "project.metadata"),
    }, publicMutationKey("project-create", idempotencyKey), signal));
  },
  async update(projectId, { title, metadata, idempotencyKey = "" }, signal) {
    const id = publicRecordId(projectId, PUBLIC_PROJECT_ID, "project.id");
    const body = {
      ...(title === undefined ? {} : { title: nonEmptyText(title, "project.title", 200) }),
      ...(metadata === undefined ? {} : { metadata: clonePublicValue(metadata, "project.metadata") }),
    };
    if (!Object.keys(body).length) throw new KolibriApiError("project.update: нет изменений");
    return publicSessionJson(`${API_ENDPOINTS.publicProjects}/${encodeURIComponent(id)}`, publicMutationOptions(
      "POST", body, publicMutationKey("project-update", idempotencyKey), signal,
    ));
  },
  remove(projectId, idempotencyKey = "", signal) {
    const id = publicRecordId(projectId, PUBLIC_PROJECT_ID, "project.id");
    return publicSessionJson(`${API_ENDPOINTS.publicProjects}/${encodeURIComponent(id)}/delete`, publicMutationOptions(
      "POST", undefined, publicMutationKey("project-delete", idempotencyKey), signal,
    ));
  },
  restore(projectId, idempotencyKey = "", signal) {
    const id = publicRecordId(projectId, PUBLIC_PROJECT_ID, "project.id");
    return publicSessionJson(`${API_ENDPOINTS.publicProjects}/${encodeURIComponent(id)}/restore`, publicMutationOptions(
      "POST", undefined, publicMutationKey("project-restore", idempotencyKey), signal,
    ));
  },
  async listMessages(projectId, signal) {
    const id = publicRecordId(projectId, PUBLIC_PROJECT_ID, "project.id");
    const payload = await publicSessionJson(`${API_ENDPOINTS.publicProjects}/${encodeURIComponent(id)}/messages`, { cache: "no-store", signal });
    return Array.isArray(payload?.data) ? payload.data : [];
  },
  getMessage(projectId, messageId, signal) {
    const project = publicRecordId(projectId, PUBLIC_PROJECT_ID, "project.id");
    const message = publicRecordId(messageId, PUBLIC_MESSAGE_ID, "message.id");
    return publicSessionJson(
      `${API_ENDPOINTS.publicProjects}/${encodeURIComponent(project)}/messages/${encodeURIComponent(message)}`,
      { cache: "no-store", signal },
    );
  },
  createMessage(projectId, { role, content, status = "completed", responseId = null, metadata = {}, idempotencyKey = "" }, signal) {
    const id = publicRecordId(projectId, PUBLIC_PROJECT_ID, "project.id");
    return publicSessionJson(`${API_ENDPOINTS.publicProjects}/${encodeURIComponent(id)}/messages`, publicMutationOptions("POST", {
      role: enumValue(role, PUBLIC_MESSAGE_ROLES, "message.role"),
      content: nonEmptyText(content, "message.content", 100_000),
      status: enumValue(status, PUBLIC_MESSAGE_STATUSES, "message.status"),
      ...(responseId ? { response_id: nonEmptyText(responseId, "message.response_id", 200) } : {}),
      metadata: clonePublicValue(metadata, "message.metadata"),
    }, publicMutationKey("message-create", idempotencyKey), signal));
  },
  updateMessage(projectId, messageId, { content, status, responseId, metadata, idempotencyKey = "" }, signal) {
    const project = publicRecordId(projectId, PUBLIC_PROJECT_ID, "project.id");
    const message = publicRecordId(messageId, PUBLIC_MESSAGE_ID, "message.id");
    const body = {
      ...(content === undefined ? {} : { content: nonEmptyText(content, "message.content", 100_000) }),
      ...(status === undefined ? {} : { status: enumValue(status, PUBLIC_MESSAGE_STATUSES, "message.status") }),
      ...(responseId === undefined ? {} : { response_id: responseId ? nonEmptyText(responseId, "message.response_id", 200) : null }),
      ...(metadata === undefined ? {} : { metadata: clonePublicValue(metadata, "message.metadata") }),
    };
    if (!Object.keys(body).length) throw new KolibriApiError("message.update: нет изменений");
    return publicSessionJson(`${API_ENDPOINTS.publicProjects}/${encodeURIComponent(project)}/messages/${encodeURIComponent(message)}`, publicMutationOptions(
      "POST", body, publicMutationKey("message-update", idempotencyKey), signal,
    ));
  },
  removeMessage(projectId, messageId, idempotencyKey = "", signal) {
    const project = publicRecordId(projectId, PUBLIC_PROJECT_ID, "project.id");
    const message = publicRecordId(messageId, PUBLIC_MESSAGE_ID, "message.id");
    return publicSessionJson(`${API_ENDPOINTS.publicProjects}/${encodeURIComponent(project)}/messages/${encodeURIComponent(message)}/delete`, publicMutationOptions(
      "POST", undefined, publicMutationKey("message-delete", idempotencyKey), signal,
    ));
  },
  restoreMessage(projectId, messageId, idempotencyKey = "", signal) {
    const project = publicRecordId(projectId, PUBLIC_PROJECT_ID, "project.id");
    const message = publicRecordId(messageId, PUBLIC_MESSAGE_ID, "message.id");
    return publicSessionJson(`${API_ENDPOINTS.publicProjects}/${encodeURIComponent(project)}/messages/${encodeURIComponent(message)}/restore`, publicMutationOptions(
      "POST", undefined, publicMutationKey("message-restore", idempotencyKey), signal,
    ));
  },
});

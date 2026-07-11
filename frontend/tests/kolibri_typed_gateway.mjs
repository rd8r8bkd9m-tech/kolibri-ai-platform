import assert from "node:assert/strict";

import {
  API_ENDPOINTS,
  KolibriApiError,
  buildAppTask,
  buildConversationMessages,
  buildDeterministicEstimateTask,
  buildDocumentTask,
  buildEstimateProposalTask,
  buildEstimateTask,
  buildSiteTask,
  loadSupportedExecutionModes,
  normalizeTypedTaskEnvelope,
  resetPublicSessionForTests,
  sendKolibriRequest,
} from "../src/runtime/kolibriApi.js";

const sha = (value) => value.repeat(64);

function verifiedArtifact(deliverableType, marker = "a") {
  return {
    kind: "file",
    name: `${deliverableType}.bin`,
    locator: `artifact://verified/${deliverableType}.bin`,
    media_type: "application/octet-stream",
    reference_sha256: sha(marker),
    content_sha256: sha(marker === "a" ? "b" : "c"),
    size_bytes: 128,
    deliverable_type: deliverableType,
    evidence_binding_sha256: sha(marker === "a" ? "d" : "e"),
    status: "materialized",
  };
}

function typedEnvelope({
  intent = "document",
  result = { type: "verified_provider_response", text: "Готов проверенный результат." },
  requested = ["pdf"],
  delivered = ["pdf"],
  artifacts = [verifiedArtifact("pdf")],
  status = "completed",
  persistence = null,
} = {}) {
  return {
    schema_version: "kolibri.public-task.v1",
    intent,
    status,
    execution: {
      status: "completed",
      model: "kolibri",
      provider_verified: true,
      output_sha256: sha("f"),
      verifier_binding_sha256: sha("1"),
      provider: "must-not-cross-the-shell-boundary",
    },
    result: { ...result, provider: "must-not-cross-the-shell-boundary" },
    ...(persistence ? { persistence } : {}),
    artifacts,
    artifact_delivery: {
      required: requested.length > 0,
      status: requested.length ? "materialized" : "not_required",
      requested,
      delivered,
      missing: requested.filter((item) => !delivered.includes(item)),
      count: artifacts.length,
    },
  };
}

function response(status, payload) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get() { return "application/json"; } },
    async json() { return payload; },
  };
}

function openAiResponse(text, task = null) {
  return {
    id: `resp_${text.length}`,
    object: "response",
    created_at: 1,
    status: "completed",
    model: "kolibri",
    output: [{
      id: `msg_${text.length}`,
      type: "message",
      status: "completed",
      role: "assistant",
      content: [{ type: "output_text", text, annotations: [] }],
    }],
    output_text: text,
    ...(task ? { task } : {}),
  };
}

function sseResponse(payload) {
  const text = payload.output_text;
  const events = [
    ["response.created", { type: "response.created", response: { ...payload, status: "in_progress", output: [] } }],
    ["response.output_text.delta", { type: "response.output_text.delta", delta: text }],
    ["response.completed", { type: "response.completed", response: payload }],
  ].map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join("");
  return new globalThis.Response(events, {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

const publicSession = {
  id: "psess_test",
  object: "public.session",
  expires_at: 9_999_999_999,
  project: { id: "project_ephemeral_test", object: "project.ephemeral", durable: false },
};

assert.equal(API_ENDPOINTS.response, "/v1/responses");
assert.equal(API_ENDPOINTS.publicSession, "/v1/public/session");

assert.deepEqual(buildConversationMessages([
  { role: "user", text: "Первый вопрос" },
  { role: "assistant", text: "Первый ответ", status: "completed" },
  { role: "assistant", text: "Не отправлять", status: "running" },
], "Второй вопрос"), [
  { role: "user", content: "Первый вопрос" },
  { role: "assistant", content: "Первый ответ" },
  { role: "user", content: "Второй вопрос" },
]);

const estimate = buildDeterministicEstimateTask({
  title: "Ремонт кухни",
  currency: "RUB",
  lines: [{
    id: "labor-1",
    description: "Монтаж",
    category: "labor",
    unit: "м2",
    quantity: "2.5",
    unitPriceMinor: 15_000,
    provenance: { source: "manual" },
  }],
  overheadRateBps: 1_000,
  taxRateBps: 2_000,
  requestedArtifacts: ["pdf", "xlsx"],
});
assert.equal(estimate.intent, "estimate");
assert.equal(estimate.spec.lines[0].quantity, "2.5");
assert.equal(estimate.spec.lines[0].unit_price_minor, 15_000);
assert.equal(estimate.spec.overhead_rate_bps, 1_000);
assert.equal("totals" in estimate.spec, false, "the browser must not calculate money");
assert.equal("provider" in estimate, false);
assert.equal(buildEstimateTask, buildDeterministicEstimateTask);
assert.deepEqual(buildEstimateProposalTask({ brief: "Смета на кухню" }), {
  intent: "estimate",
  brief: "Смета на кухню",
  requested_artifacts: ["pdf"],
});

const normalizedEstimate = normalizeTypedTaskEnvelope(typedEnvelope({
  intent: "estimate",
  requested: [],
  delivered: [],
  artifacts: [],
  result: {
    type: "deterministic_estimate",
    estimate: {
      title: "Ремонт кухни",
      currency: "RUB",
      minor_unit: 2,
      region: "Москва",
      source_summary: "Цены требуют проверки",
      assumptions: [],
      questions: [],
      lines: estimate.spec.lines,
      overhead_rate_bps: 1_000,
      tax_rate_bps: 2_000,
    },
    calculation: {
      engine: "kolibri.decimal-minor-unit.v1",
      money_authority: "deterministic_calculator",
      llm_calculates_money: false,
      totals: { grand_total_minor: 59_400 },
    },
  },
  persistence: {
    estimate_id: "estimate-test",
    version_id: "estimate-version-test",
    version: 1,
    state: "saved",
    spec_sha256: sha("2"),
    calculation_sha256: sha("3"),
  },
}), "estimate");
assert.equal(normalizedEstimate.status, "completed");
assert.equal(normalizedEstimate.result.calculation.totals.grand_total_minor, 59_400);
assert.equal(normalizedEstimate.result.estimate.lines.length, 1);
assert.equal(normalizedEstimate.persistence.version, 1);
assert.throws(
  () => normalizeTypedTaskEnvelope(typedEnvelope({
    intent: "estimate",
    requested: [],
    delivered: [],
    artifacts: [],
    result: { type: "deterministic_estimate", calculation: { money_authority: "llm", llm_calculates_money: true } },
  }), "estimate"),
  (error) => error instanceof KolibriApiError && /детерминированным/.test(error.message),
);

assert.deepEqual(buildDocumentTask({ brief: "Коммерческое предложение", documentType: "commercial-offer" }), {
  intent: "document",
  brief: "Коммерческое предложение",
  document_type: "commercial-offer",
  format: "pdf",
  content: {},
});
assert.deepEqual(buildSiteTask({ brief: "Сайт компании" }).requested_artifacts, ["source", "site-preview"]);
assert.deepEqual(buildAppTask({ brief: "CRM" }).requested_artifacts, ["source", "build", "test-report"]);
assert.throws(
  () => buildSiteTask({ brief: "Сайт", requirements: { apiKey: "must-not-leave-browser" } }),
  (error) => error instanceof KolibriApiError && /credential/.test(error.message),
);
assert.throws(
  () => buildAppTask({ brief: "CRM", provider: "mimo" }),
  (error) => error instanceof KolibriApiError && /gateway/.test(error.message),
);

const normalized = normalizeTypedTaskEnvelope(typedEnvelope(), "document");
assert.equal(normalized.status, "completed");
assert.equal(normalized.execution.model, "kolibri");
assert.equal(normalized.execution.provider_verified, true);
assert.equal("provider" in normalized.execution, false);
assert.deepEqual(normalized.result, { type: "verified_provider_response", text: "Готов проверенный результат." });
assert.equal("provider" in normalized.result, false);
assert.equal(normalized.artifacts.length, 1);

const forgedPreview = {
  ...verifiedArtifact("site-preview", "2"),
  evidence_binding_sha256: "not-a-sha256",
};
const partialSite = normalizeTypedTaskEnvelope(typedEnvelope({
  intent: "site",
  requested: ["source", "site-preview"],
  delivered: ["source", "site-preview"],
  artifacts: [verifiedArtifact("source", "3"), forgedPreview],
}), "site");
assert.equal(partialSite.status, "incomplete", "invalid evidence must never preserve completed");
assert.deepEqual(partialSite.artifact_delivery.delivered, ["source"]);
assert.deepEqual(partialSite.artifact_delivery.missing, ["site-preview"]);
assert.equal(partialSite.artifacts.length, 1);

const originalFetch = globalThis.fetch;
try {
  const calls = [];
  globalThis.fetch = async (url) => {
    calls.push({ url });
    return response(200, { models: [{ id: "kolibri" }] });
  };
  assert.deepEqual(await loadSupportedExecutionModes(), ["fast"], "Codex must stay disabled without an advertised capability");
  assert.deepEqual(calls.map((call) => call.url), ["/v1/models"]);

  calls.length = 0;
  globalThis.fetch = async (url) => {
    calls.push({ url });
    return response(200, { models: [{ id: "kolibri", supported_execution_modes: ["fast", "codex"] }] });
  };
  assert.deepEqual(await loadSupportedExecutionModes(), ["fast", "codex"]);
  assert.deepEqual(calls.map((call) => call.url), ["/v1/models"]);

  calls.length = 0;
  resetPublicSessionForTests();
  globalThis.fetch = async (url, options) => {
    calls.push({ url, body: options?.body ? JSON.parse(options.body) : null });
    if (url === "/v1/public/session") return response(200, publicSession);
    return sseResponse(openAiResponse("ignored in favor of typed verified result", typedEnvelope()));
  };

  const result = await sendKolibriRequest({
    text: "Сделай КП",
    task: buildDocumentTask({ brief: "КП на ремонт", documentType: "commercial-offer" }),
  });
  assert.deepEqual(calls.map((call) => call.url), ["/v1/public/session", "/v1/responses"]);
  const typedCall = calls[1];
  assert.equal(typedCall.body.model, "kolibri");
  assert.equal(typedCall.body.stream, true);
  assert.equal(typedCall.body.task.intent, "document");
  assert.equal("provider" in typedCall.body, false);
  assert.equal(result.endpoint, "/v1/responses");
  assert.equal(result.text, "Готов проверенный результат.");
  assert.equal(result.task.status, "completed");
  assert.equal(result.artifacts.length, 1);
  assert.equal("raw" in result, false);
  assert.equal("provenance" in result, false);

  calls.length = 0;
  resetPublicSessionForTests();
  const pdfArtifact = {
    ...verifiedArtifact("pdf", "4"),
    id: "artifact-estimate-pdf",
    kind: "pdf",
    name: "estimate-v1.pdf",
    locator: "/v1/public/estimate-artifacts/artifact-estimate-pdf/content",
    media_type: "application/pdf",
    immutable: true,
    estimate_id: "estimate-one",
    estimate_version: 1,
  };
  const estimateEnvelope = typedEnvelope({
    intent: "estimate",
    requested: ["pdf"],
    delivered: ["pdf"],
    artifacts: [pdfArtifact],
    result: {
      type: "deterministic_estimate",
      estimate: normalizedEstimate.result.estimate,
      calculation: normalizedEstimate.result.calculation,
    },
    persistence: {
      estimate_id: "estimate-one",
      version_id: "estimate-version-one",
      version: 1,
      state: "saved",
      spec_sha256: sha("5"),
      calculation_sha256: sha("6"),
    },
  });
  globalThis.fetch = async (url, options) => {
    calls.push({ url, body: options?.body ? JSON.parse(options.body) : null });
    if (url === "/v1/public/session") return response(200, publicSession);
    return sseResponse(openAiResponse("raw provider JSON", estimateEnvelope));
  };
  const estimateResult = await sendKolibriRequest({
    text: "Составь смету на кухню",
    task: buildEstimateProposalTask({ brief: "Кухня 18 м2" }),
    executionMode: "codex",
  });
  assert.equal(calls[1].body.execution_mode, "codex");
  assert.deepEqual(calls[1].body.task.requested_artifacts, ["pdf"]);
  assert.match(estimateResult.text, /итог рассчитан детерминированно/);
  assert.equal(estimateResult.task.persistence.estimate_id, "estimate-one");
  assert.equal(estimateResult.artifacts[0].locator, pdfArtifact.locator);
  assert.equal(estimateResult.artifacts[0].immutable, true);

  calls.length = 0;
  resetPublicSessionForTests();
  globalThis.fetch = async (url) => {
    calls.push({ url });
    if (url === "/v1/public/session") return response(200, publicSession);
    return response(503, { error: { message: "gateway unavailable" } });
  };
  await assert.rejects(
    sendKolibriRequest({ text: "Сделай сайт", task: buildSiteTask({ brief: "Сайт" }) }),
    (error) => error instanceof KolibriApiError && error.message === "gateway unavailable",
  );
  assert.deepEqual(calls.map((call) => call.url), ["/v1/public/session", "/v1/responses"]);
  assert.ok(calls.every((call) => !call.url.includes("/api/chat") && !call.url.includes("/v1/chat/completions")));

  calls.length = 0;
  resetPublicSessionForTests();
  globalThis.fetch = async (url, options) => {
    calls.push({ url, body: options?.body ? JSON.parse(options.body) : null });
    if (url === "/v1/public/session") return response(200, publicSession);
    return sseResponse(openAiResponse("Обычный ответ Kolibri"));
  };
  const conversational = await sendKolibriRequest({ text: "Ответь на вопрос" });
  assert.deepEqual(calls.map((call) => call.url), ["/v1/public/session", "/v1/responses"]);
  assert.equal(calls[1].body.model, "kolibri");
  assert.equal(conversational.text, "Обычный ответ Kolibri");
  assert.deepEqual(conversational.artifacts, [], "untyped artifact claims must not enter the Shell");

  calls.length = 0;
  resetPublicSessionForTests();
  let responseAttempts = 0;
  globalThis.fetch = async (url, options) => {
    calls.push({
      url,
      method: options?.method || "GET",
      headers: options?.headers || {},
      body: options?.body ? JSON.parse(options.body) : null,
    });
    if (url === "/v1/public/session") return response(200, publicSession);
    responseAttempts += 1;
    if (responseAttempts === 1) return response(401, { detail: "public_session_required_or_expired" });
    return sseResponse(openAiResponse("Сессия восстановлена."));
  };
  const recovered = await sendKolibriRequest({ text: "привет" });
  assert.equal(recovered.text, "Сессия восстановлена.");
  assert.deepEqual(calls.map((call) => `${call.method} ${call.url}`), [
    "GET /v1/public/session",
    "POST /v1/responses",
    "POST /v1/public/session",
    "POST /v1/responses",
  ]);
  assert.equal(calls[1].body.idempotency_key, calls[3].body.idempotency_key);
  assert.equal(calls[1].headers["Idempotency-Key"], calls[3].headers["Idempotency-Key"]);

  for (const [status, payload] of [
    [401, { detail: "invalid_provider_credentials" }],
    [403, { detail: "public_session_required_or_expired" }],
    [403, { detail: "origin_not_allowed" }],
    [503, { detail: "public_session_required_or_expired" }],
  ]) {
    calls.length = 0;
    resetPublicSessionForTests();
    globalThis.fetch = async (url, options) => {
      calls.push({ url, method: options?.method || "GET" });
      if (url === "/v1/public/session") return response(200, publicSession);
      return response(status, payload);
    };
    await assert.rejects(
      sendKolibriRequest({ text: "не ретраить эту ошибку" }),
      (error) => error instanceof KolibriApiError && error.status === status,
    );
    assert.deepEqual(calls.map((call) => `${call.method} ${call.url}`), [
      "GET /v1/public/session",
      "POST /v1/responses",
    ]);
  }

  calls.length = 0;
  resetPublicSessionForTests();
  globalThis.fetch = async (url, options) => {
    calls.push({ url, method: options?.method || "GET" });
    if (url === "/v1/public/session") return response(200, publicSession);
    return response(401, { error: { code: "public_session_required_or_expired" } });
  };
  await assert.rejects(
    sendKolibriRequest({ text: "повторить только один раз" }),
    (error) => error instanceof KolibriApiError
      && error.status === 401
      && error.message === "HTTP 401",
  );
  assert.deepEqual(calls.map((call) => `${call.method} ${call.url}`), [
    "GET /v1/public/session",
    "POST /v1/responses",
    "POST /v1/public/session",
    "POST /v1/responses",
  ]);

  calls.length = 0;
  resetPublicSessionForTests();
  let releaseFirstWave;
  const firstWaveReady = new Promise((resolve) => { releaseFirstWave = resolve; });
  let firstWaveCount = 0;
  let refreshCount = 0;
  const responseCountByKey = new Map();
  globalThis.fetch = async (url, options) => {
    const method = options?.method || "GET";
    const key = options?.headers?.["Idempotency-Key"] || "";
    calls.push({ url, method, key, body: options?.body ? JSON.parse(options.body) : null });
    if (url === "/v1/public/session") {
      if (method === "POST") refreshCount += 1;
      return response(200, publicSession);
    }
    const attempt = (responseCountByKey.get(key) || 0) + 1;
    responseCountByKey.set(key, attempt);
    if (attempt === 1) {
      firstWaveCount += 1;
      if (firstWaveCount === 2) releaseFirstWave();
      await firstWaveReady;
      return response(401, { detail: { code: "public_session_required_or_expired" } });
    }
    return sseResponse(openAiResponse(`Восстановлен ${JSON.parse(options.body).input.at(-1).content}`));
  };
  const parallel = await Promise.all([
    sendKolibriRequest({ text: "первый" }),
    sendKolibriRequest({ text: "второй" }),
  ]);
  assert.deepEqual(parallel.map((item) => item.text), ["Восстановлен первый", "Восстановлен второй"]);
  assert.equal(refreshCount, 1, "parallel expiry must share one refresh POST");
  assert.equal(calls.filter((call) => call.method === "GET" && call.url === "/v1/public/session").length, 1);
  assert.equal(calls.filter((call) => call.url === "/v1/responses").length, 4);
  assert.equal(responseCountByKey.size, 2);
  assert.ok([...responseCountByKey.values()].every((count) => count === 2));

  calls.length = 0;
  resetPublicSessionForTests();
  globalThis.fetch = async (url, options) => {
    calls.push({ url, method: options?.method || "GET" });
    if (url === "/v1/public/session" && (options?.method || "GET") === "POST") {
      return response(401, { detail: "public_session_creation_denied" });
    }
    if (url === "/v1/public/session") return response(200, publicSession);
    return response(401, { detail: "public_session_required_or_expired" });
  };
  await assert.rejects(
    sendKolibriRequest({ text: "refresh запрещён" }),
    (error) => error instanceof KolibriApiError
      && error.status === 401
      && error.message === "public_session_creation_denied",
  );
  assert.deepEqual(calls.map((call) => `${call.method} ${call.url}`), [
    "GET /v1/public/session",
    "POST /v1/responses",
    "POST /v1/public/session",
  ]);

  calls.length = 0;
  resetPublicSessionForTests();
  globalThis.fetch = async (url, options) => {
    calls.push({ url, body: options?.body ? JSON.parse(options.body) : null });
    if (url === "/v1/public/session") return response(200, publicSession);
    return sseResponse(openAiResponse("Второй ответ"));
  };
  await sendKolibriRequest({
    text: "Второй вопрос",
    messages: [
      { role: "user", text: "Первый вопрос" },
      { role: "assistant", text: "Первый ответ", status: "completed" },
    ],
    executionMode: "codex",
  });
  assert.equal(calls[1].body.execution_mode, "codex");
  assert.deepEqual(calls[1].body.input, [
    { role: "user", content: "Первый вопрос" },
    { role: "assistant", content: "Первый ответ" },
    { role: "user", content: "Второй вопрос" },
  ]);
  assert.equal(calls[1].body.input.filter((message) => message.content === "Второй вопрос").length, 1);

  calls.length = 0;
  resetPublicSessionForTests();
  globalThis.fetch = async (url, options) => {
    calls.push({ url, method: options?.method || "GET", body: options?.body ? JSON.parse(options.body) : null });
    if (url === "/v1/public/session") return response(200, publicSession);
    const latest = JSON.parse(options.body).input.at(-1).content;
    return sseResponse(openAiResponse(latest === "56+67" ? "123" : "Всё хорошо."));
  };
  const liveChat = await sendKolibriRequest({ text: "как дела в москве?" });
  const liveMath = await sendKolibriRequest({ text: "56+67", executionMode: "codex" });
  assert.equal(liveChat.text, "Всё хорошо.");
  assert.equal(liveMath.text, "123");
  assert.deepEqual(
    calls.filter((call) => call.url === "/v1/responses").map((call) => call.method),
    ["POST", "POST"],
  );
  assert.ok(calls.every((call) => !call.url.includes("/api/chat")));

  calls.length = 0;
  resetPublicSessionForTests();
  const cancelled = new AbortController();
  cancelled.abort(new Error("caller cancelled"));
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, method: options.method || "GET", hasSignal: Boolean(options.signal) });
    if (options.signal?.aborted) throw options.signal.reason;
    if (url === "/v1/public/session") return response(200, publicSession);
    return sseResponse(openAiResponse("Независимый запрос выполнен."));
  };
  await assert.rejects(sendKolibriRequest({ text: "отменить", signal: cancelled.signal }));
  const afterCancellation = await sendKolibriRequest({ text: "продолжить" });
  assert.equal(afterCancellation.text, "Независимый запрос выполнен.");
  assert.equal(
    calls.filter((call) => call.url === "/v1/public/session").length,
    1,
    "a caller abort must not invalidate the shared public-session handshake",
  );
  assert.equal(calls.find((call) => call.url === "/v1/public/session").hasSignal, false);

  let fetchCalled = false;
  globalThis.fetch = async () => { fetchCalled = true; return response(500, {}); };
  await assert.rejects(
    sendKolibriRequest({
      text: "Сделай сайт",
      task: { ...buildSiteTask({ brief: "Сайт" }), provider: "mimo" },
    }),
    (error) => error instanceof KolibriApiError && /gateway/.test(error.message),
  );
  assert.equal(fetchCalled, false, "routing selection must be rejected before transport");
} finally {
  globalThis.fetch = originalFetch;
}

console.log("Kolibri typed Shell gateway contracts passed");

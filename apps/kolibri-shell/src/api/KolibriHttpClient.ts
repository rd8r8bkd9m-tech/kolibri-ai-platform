import { parseSseStream, type SseMessage } from './sse';
import type {
  BootstrapSnapshot,
  CapabilityRecord,
  EstimateArtifactData,
  EstimateLine,
  EstimateSummarySection,
  KolibriClient,
  ProjectSummary,
  ResponseRequest,
  ResponseStreamHandlers,
  VerifiedArtifact,
  WorkStage,
  WorkTraceUpdate,
} from './types';

type JsonRecord = Record<string, unknown>;

export const SHELL_BOOTSTRAP_ENDPOINT = '/v1/shell/bootstrap';

function record(value: unknown): JsonRecord {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};
}

function arrayFromEnvelope(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  const body = record(value);
  const data = body.data;
  if (Array.isArray(data)) return data;
  const nested = record(data);
  if (Array.isArray(nested.data)) return nested.data;
  if (Array.isArray(body.items)) return body.items;
  return [];
}

function safeString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function normalizeCapabilities(value: unknown): CapabilityRecord[] {
  return arrayFromEnvelope(value)
    .map(record)
    .map((item): CapabilityRecord => {
      const evidenceGate = record(item.evidence_gate);
      const evidenceReady = Object.keys(evidenceGate).length > 0
        && Object.values(evidenceGate).every((state) => state === true);
      const status: CapabilityRecord['status'] =
        item.status === 'available' || item.status === 'degraded'
          ? item.status
          : item.available === true && evidenceReady
            ? 'available'
          : 'unavailable';
      const kind: CapabilityRecord['kind'] =
        item.kind === 'plugin' || item.kind === 'skill' || item.kind === 'tool'
          ? item.kind
          : 'capability';
      return {
        id: safeString(item.id) ?? '',
        name: safeString(item.name) ?? safeString(item.label) ?? safeString(item.id) ?? '',
        description: safeString(item.description),
        status,
        invocable: item.invocable === true || (item.available === true && evidenceReady),
        kind,
      };
    })
    .filter((item) => item.id && item.name);
}

function normalizeProjects(value: unknown): ProjectSummary[] {
  return arrayFromEnvelope(value)
    .map(record)
    .map((item) => ({
      id: safeString(item.id) ?? '',
      title: safeString(item.title) ?? safeString(item.name) ?? 'Без названия',
      updatedAt:
        safeString(item.updated_at) ?? safeString(item.updatedAt) ?? new Date(0).toISOString(),
    }))
    .filter((item) => item.id);
}

function isSafeArtifactUrl(value: string): boolean {
  if (value.startsWith('/')) return !value.startsWith('//');
  try {
    const url = new URL(value, window.location.origin);
    return url.origin === window.location.origin && ['http:', 'https:'].includes(url.protocol);
  } catch {
    return false;
  }
}

function safePositiveNumber(value: unknown): number | undefined {
  const number = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(number) && number >= 0 ? number : undefined;
}

function normalizeEstimateLine(value: unknown, index: number): EstimateLine | null {
  const item = record(value);
  const title = safeString(item.title) ?? safeString(item.name) ?? safeString(item.description);
  const unit = safeString(item.unit) ?? safeString(item.unit_name);
  const quantity = safePositiveNumber(item.quantity);
  const unitPriceRub = safePositiveNumber(item.unit_price_rub ?? item.unitPriceRub ?? item.unit_price);
  const amountRub = safePositiveNumber(item.amount_rub ?? item.amountRub ?? item.amount);
  if (!title || !unit || quantity === undefined || unitPriceRub === undefined || amountRub === undefined) {
    return null;
  }
  return {
    id: safeString(item.id) ?? `line-${index + 1}`,
    title,
    unit,
    quantity,
    unitPriceRub,
    amountRub,
    section: safeString(item.section),
  };
}

function normalizeEstimateSummary(value: unknown, index: number): EstimateSummarySection | null {
  const item = record(value);
  const title = safeString(item.title) ?? safeString(item.name);
  const amountRub = safePositiveNumber(item.amount_rub ?? item.amountRub ?? item.amount);
  if (!title || amountRub === undefined) return null;
  const icon =
    item.icon === 'foundation' || item.icon === 'house' || item.icon === 'engineering'
      ? item.icon
      : undefined;
  return { id: safeString(item.id) ?? `section-${index + 1}`, title, amountRub, icon };
}

function normalizeEstimateData(value: unknown): EstimateArtifactData | undefined {
  const item = record(value);
  const title = safeString(item.title);
  const sourceSummary = safeString(item.source_summary) ?? safeString(item.sourceSummary);
  const rawLines = Array.isArray(item.lines) ? item.lines : [];
  const lines = rawLines
    .map((line, index) => normalizeEstimateLine(line, index))
    .filter((line): line is EstimateLine => line !== null);
  if (!title || !sourceSummary || !lines.length || lines.length !== rawLines.length) return undefined;
  const rawSummary = Array.isArray(item.summary_sections)
    ? item.summary_sections
    : Array.isArray(item.summarySections)
      ? item.summarySections
      : [];
  const summarySections = rawSummary
    .map((section, index) => normalizeEstimateSummary(section, index))
    .filter((section): section is EstimateSummarySection => section !== null);
  if (rawSummary.length && summarySections.length !== rawSummary.length) return undefined;
  return {
    title,
    location: safeString(item.location),
    pricedAt: safeString(item.priced_at) ?? safeString(item.pricedAt),
    status: item.status === 'verified' ? 'verified' : 'preliminary',
    sourceSummary,
    lines,
    summarySections: summarySections.length ? summarySections : undefined,
  };
}

export function normalizeVerifiedArtifact(value: unknown): VerifiedArtifact | null {
  const item = record(value);
  const id = safeString(item.id) ?? safeString(item.artifact_id);
  const name = safeString(item.name) ?? safeString(item.filename);
  const mimeType = safeString(item.mime_type) ?? safeString(item.mimeType);
  const mimeTypeWithAliases = mimeType ?? safeString(item.media_type);
  const sha256 = safeString(item.sha256) ?? safeString(item.content_sha256);
  const downloadUrl =
    safeString(item.download_url) ??
    safeString(item.downloadUrl) ??
    safeString(item.locator) ??
    safeString(item.url);
  const previewUrl = safeString(item.preview_url) ?? safeString(item.previewUrl);
  const sizeBytes = Number(item.size_bytes ?? item.sizeBytes);

  if (
    !id ||
    !name ||
    !mimeTypeWithAliases ||
    !sha256?.match(/^[a-f0-9]{64}$/) ||
    !Number.isSafeInteger(sizeBytes) ||
    sizeBytes <= 0 ||
    !downloadUrl ||
    !isSafeArtifactUrl(downloadUrl) ||
    (previewUrl && !isSafeArtifactUrl(previewUrl))
  ) {
    return null;
  }

  const artifactType = safeString(item.kind) ?? safeString(item.artifact_type) ?? safeString(item.type);
  const estimate = artifactType === 'estimate'
    ? normalizeEstimateData(item.estimate ?? item.data)
    : undefined;
  if (artifactType === 'estimate' && !estimate) return null;

  return {
    id,
    name,
    mimeType: mimeTypeWithAliases,
    sha256,
    sizeBytes,
    downloadUrl,
    previewUrl,
    kind: estimate ? 'estimate' : 'file',
    estimate,
  };
}

function getEventType(message: SseMessage): string {
  const payload = record(message.data);
  return safeString(payload.type) ?? message.event;
}

function getNestedPayload(message: SseMessage): JsonRecord {
  const payload = record(message.data);
  return Object.keys(record(payload.data)).length ? record(payload.data) : payload;
}

function traceUpdate(type: string, payload: JsonRecord): WorkTraceUpdate | null {
  const stageFromPayload = safeString(payload.stage);
  const stageMap: Record<string, WorkStage> = {
    'response.created': 'queued',
    'response.status.updated': 'working',
    'response.work_summary.updated': 'working',
    'response.tool.started': 'tool',
    'response.tool.completed': 'tool',
    'response.source.added': 'source',
    'response.verification.updated': 'verifying',
    'response.completed': 'complete',
    'response.failed': 'blocked',
  };
  const stage =
    stageFromPayload &&
    ['queued', 'planning', 'working', 'tool', 'source', 'verifying', 'complete', 'blocked'].includes(
      stageFromPayload,
    )
      ? (stageFromPayload as WorkStage)
      : stageMap[type];
  if (!stage) return null;

  const statusValue = safeString(payload.status);
  const status =
    statusValue === 'complete' || statusValue === 'failed' || statusValue === 'pending'
      ? statusValue
      : type.endsWith('.completed') || type === 'response.completed'
        ? 'complete'
        : type === 'response.failed'
          ? 'failed'
          : 'active';

  return {
    id: safeString(payload.id) ?? `${stage}:${safeString(payload.name) ?? type}`,
    stage,
    label:
      safeString(payload.label) ??
      safeString(payload.name) ??
      ({
        queued: 'Задача принята',
        planning: 'Составляю план',
        working: 'Выполняю задачу',
        tool: 'Использую инструмент',
        source: 'Проверяю источник',
        verifying: 'Проверяю результат',
        complete: 'Готово',
        blocked: 'Нужна помощь',
        cancelled: 'Остановлено',
      }[stage] as string),
    summary: safeString(payload.summary) ?? safeString(payload.message),
    status,
  };
}

function textFromResponseJson(value: unknown): string {
  const body = record(value);
  const direct = safeString(body.output_text) ?? safeString(body.text);
  if (direct) return direct;
  const output = Array.isArray(body.output) ? body.output : [];
  const chunks: string[] = [];
  for (const itemValue of output) {
    const item = record(itemValue);
    const content = Array.isArray(item.content) ? item.content : [];
    for (const contentValue of content) {
      const contentItem = record(contentValue);
      const text = safeString(contentItem.text);
      if (text) chunks.push(text);
    }
  }
  return chunks.join('\n');
}

function errorMessage(body: unknown, status: number): string {
  const payload = record(body);
  const error = record(payload.error);
  return (
    safeString(error.message) ??
    safeString(payload.message) ??
    `Kolibri API вернул HTTP ${status}. Попробуйте ещё раз.`
  );
}

export class KolibriHttpClient implements KolibriClient {
  constructor(
    private readonly baseUrl = '',
    private readonly fetcher: typeof fetch = globalThis.fetch.bind(globalThis),
  ) {}

  private async json(path: string, init: RequestInit = {}): Promise<unknown> {
    const response = await this.fetcher(`${this.baseUrl}${path}`, {
      credentials: 'include',
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...init.headers,
      },
    });
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new Error(errorMessage(body, response.status));
    return body;
  }

  async bootstrap(signal?: AbortSignal): Promise<BootstrapSnapshot> {
    const session = await this.json(SHELL_BOOTSTRAP_ENDPOINT, {
      method: 'POST',
      signal,
      body: JSON.stringify({}),
    });
    const sessionBody = record(session);
    const nested = record(sessionBody.data);
    const sessionRecord = record(sessionBody.session);
    const embeddedCapabilities = Array.isArray(sessionBody.capabilities)
      ? normalizeCapabilities(sessionBody.capabilities)
      : [];
    const embeddedProjects = Array.isArray(sessionBody.projects)
      ? normalizeProjects(sessionBody.projects)
      : [];
    const [capabilityResult, projectResult] = await Promise.allSettled([
      embeddedCapabilities.length
        ? Promise.resolve(sessionBody.capabilities)
        : this.json('/v1/capabilities', { signal }),
      embeddedProjects.length
        ? Promise.resolve(sessionBody.projects)
        : this.json('/v1/projects', { signal }),
    ]);
    return {
      sessionId:
        safeString(sessionBody.id) ??
        safeString(sessionRecord.id) ??
        safeString(nested.id) ??
        safeString(nested.session_id),
      capabilities:
        capabilityResult.status === 'fulfilled'
          ? normalizeCapabilities(capabilityResult.value)
          : [],
      projects:
        projectResult.status === 'fulfilled' ? normalizeProjects(projectResult.value) : [],
    };
  }

  async createProject(title: string, signal?: AbortSignal): Promise<ProjectSummary> {
    const payload = await this.json('/v1/projects', {
      method: 'POST',
      signal,
      body: JSON.stringify({ title, idempotency_key: crypto.randomUUID() }),
    });
    const item = record(record(payload).data);
    const id = safeString(item.id);
    if (!id) throw new Error('Kolibri API не вернул идентификатор проекта.');
    return {
      id,
      title: safeString(item.title) ?? title,
      updatedAt: safeString(item.updated_at) ?? new Date().toISOString(),
    };
  }

  async streamResponse(
    request: ResponseRequest,
    handlers: ResponseStreamHandlers,
    signal?: AbortSignal,
  ): Promise<void> {
    const idempotencyKey = crypto.randomUUID();
    const response = await this.fetcher(`${this.baseUrl}/v1/responses`, {
      method: 'POST',
      credentials: 'include',
      signal,
      headers: {
        Accept: 'text/event-stream, application/json',
        'Content-Type': 'application/json',
        'Idempotency-Key': idempotencyKey,
      },
      body: JSON.stringify({
        model: 'kolibri',
        input: request.input,
        stream: true,
        previous_response_id: request.previousResponseId ?? null,
        project_id: request.projectId,
        tools: request.tools.map((id) => ({ type: id })),
        reasoning: { effort: request.mode === 'reasoning' ? 'medium' : 'low' },
      }),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new Error(errorMessage(body, response.status));
    }

    const contentType = response.headers.get('content-type') ?? '';
    if (contentType.includes('text/event-stream') && response.body) {
      for await (const message of parseSseStream(response.body)) {
        this.consumeEvent(message, handlers);
      }
      return;
    }

    const body = await response.json();
    const item = record(body);
    const id = safeString(item.id) ?? safeString(record(item.data).id);
    if (id) handlers.onCreated(id);
    const text = textFromResponseJson(body);
    if (text) handlers.onTextDelta(text);
    handlers.onCompleted(id);
  }

  private consumeEvent(message: SseMessage, handlers: ResponseStreamHandlers): void {
    const type = getEventType(message);
    const payload = getNestedPayload(message);
    if (type === 'response.created') {
      const id = safeString(record(payload.response).id) ?? safeString(payload.id);
      if (id) handlers.onCreated(id);
    }
    if (type === 'response.output_text.delta') {
      const delta = safeString(payload.delta);
      if (delta) handlers.onTextDelta(delta);
    }
    if (type === 'response.artifact.ready') {
      const artifact = normalizeVerifiedArtifact(payload.artifact ?? payload);
      if (artifact) handlers.onArtifact(artifact);
    }
    const trace = traceUpdate(type, payload);
    if (trace) handlers.onTrace(trace);
    if (type === 'response.completed') {
      handlers.onCompleted(safeString(record(payload.response).id) ?? safeString(payload.id));
    }
    if (type === 'response.failed') {
      handlers.onFailed(
        safeString(payload.message) ?? 'Исполнение остановилось. Запрос можно повторить.',
      );
    }
  }

  async cancelResponse(responseId: string, signal?: AbortSignal): Promise<void> {
    await this.json(`/v1/responses/${encodeURIComponent(responseId)}/cancel`, {
      method: 'POST',
      signal,
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({}),
    });
  }
}

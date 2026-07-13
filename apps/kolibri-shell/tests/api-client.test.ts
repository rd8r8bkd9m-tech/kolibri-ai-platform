import { describe, expect, it, vi } from 'vitest';
import {
  KolibriHttpClient,
  normalizeVerifiedArtifact,
  SHELL_BOOTSTRAP_ENDPOINT,
} from '../src/api/KolibriHttpClient';

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

describe('KolibriHttpClient', () => {
  it('uses the native fetch transport without losing its global binding', async () => {
    const nativeFetch = vi.fn(async () => jsonResponse({ data: [] }));
    vi.stubGlobal('fetch', nativeFetch);
    const client = new KolibriHttpClient();
    await client.bootstrap();
    expect(nativeFetch).toHaveBeenCalledTimes(3);
    vi.unstubAllGlobals();
  });

  it('always establishes the public session with POST before discovery requests', async () => {
    const calls: Array<{ path: string; method: string }> = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      calls.push({ path, method: init?.method ?? 'GET' });
      if (path.endsWith(SHELL_BOOTSTRAP_ENDPOINT)) return jsonResponse({ data: { id: 'session-1' } });
      if (path.endsWith('/v1/capabilities')) {
        return jsonResponse({
          data: [
            { id: 'web_search', name: 'Интернет', status: 'available', invocable: true },
            { id: 'image', name: 'Изображение', status: 'unavailable', invocable: false },
          ],
        });
      }
      return jsonResponse({ data: [{ id: 'project-1', title: 'Дом', updated_at: '2026-07-12T00:00:00Z' }] });
    });

    const snapshot = await new KolibriHttpClient('', fetcher as typeof fetch).bootstrap();

    expect(SHELL_BOOTSTRAP_ENDPOINT).toBe('/v1/shell/bootstrap');
    expect(calls[0]).toEqual({ path: SHELL_BOOTSTRAP_ENDPOINT, method: 'POST' });
    expect(calls.slice(1).map((call) => call.path).sort()).toEqual([
      '/v1/capabilities',
      '/v1/projects',
    ]);
    expect(snapshot.sessionId).toBe('session-1');
    expect(snapshot.projects[0]?.title).toBe('Дом');
    expect(snapshot.capabilities).toHaveLength(2);
  });

  it('uses the atomic production bootstrap payload without follow-up discovery 404s', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toBe(SHELL_BOOTSTRAP_ENDPOINT);
      expect(init?.method).toBe('POST');
      expect(JSON.parse(String(init?.body))).toEqual({});
      return jsonResponse({
        session: { id: 'session-production' },
        projects: [
          { id: 'project-production', title: 'Первый проект', updated_at: '2026-07-13T00:00:00Z' },
        ],
        capabilities: [
          {
            id: 'chat',
            label: 'Диалог',
            available: true,
            evidence_gate: { route: true, executor: true, renderer: true, evidence: true },
          },
        ],
      });
    });

    const snapshot = await new KolibriHttpClient('', fetcher as typeof fetch).bootstrap();

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(snapshot.sessionId).toBe('session-production');
    expect(snapshot.projects).toEqual([
      expect.objectContaining({ id: 'project-production', title: 'Первый проект' }),
    ]);
    expect(snapshot.capabilities).toEqual([
      expect.objectContaining({ id: 'chat', name: 'Диалог', status: 'available', invocable: true }),
    ]);
  });

  it('streams text, safe work trace and a verified artifact from Responses SSE', async () => {
    const sha = 'b'.repeat(64);
    const frames = [
      `event: response.created\ndata: {"id":"response-9"}\n\n`,
      `event: response.work_summary.updated\ndata: {"id":"plan","stage":"planning","label":"Планирую","status":"active"}\n\n`,
      `event: response.output_text.delta\ndata: {"delta":"Привет"}\n\n`,
      `event: response.artifact.ready\ndata: {"artifact":{"id":"artifact-9","name":"report.pdf","mime_type":"application/pdf","size_bytes":100,"sha256":"${sha}","download_url":"/v1/artifacts/artifact-9/content"}}\n\n`,
      `event: response.completed\ndata: {"id":"response-9"}\n\n`,
    ].join('');
    const requestInits: RequestInit[] = [];
    const fetcher = vi.fn(async (...args: [RequestInfo | URL, RequestInit?]) => {
      requestInits.push(args[1] ?? {});
      return new Response(new TextEncoder().encode(frames), {
        status: 200,
        headers: { 'content-type': 'text/event-stream' },
      });
    });
    const handlers = {
      onCreated: vi.fn(),
      onTextDelta: vi.fn(),
      onTrace: vi.fn(),
      onArtifact: vi.fn(),
      onCompleted: vi.fn(),
      onFailed: vi.fn(),
    };

    await new KolibriHttpClient('', fetcher as typeof fetch).streamResponse(
      { input: 'Привет', tools: [] },
      handlers,
    );

    expect(handlers.onCreated).toHaveBeenCalledWith('response-9');
    expect(handlers.onTextDelta).toHaveBeenCalledWith('Привет');
    expect(handlers.onTrace).toHaveBeenCalledWith(expect.objectContaining({ stage: 'planning' }));
    expect(handlers.onArtifact).toHaveBeenCalledWith(expect.objectContaining({ id: 'artifact-9' }));
    expect(handlers.onCompleted).toHaveBeenCalledWith('response-9');
    expect(handlers.onFailed).not.toHaveBeenCalled();
    const requestInit = requestInits[0];
    expect(new Headers(requestInit?.headers).get('Idempotency-Key')).toBeTruthy();
    expect(JSON.parse(String(requestInit?.body))).not.toHaveProperty('idempotency_key');
  });

  it('uses header idempotency for cancellation and no body idempotency field', async () => {
    const requestInits: RequestInit[] = [];
    const fetcher = vi.fn(async (...args: [RequestInfo | URL, RequestInit?]) => {
      requestInits.push(args[1] ?? {});
      return jsonResponse({ status: 'cancelled' });
    });
    await new KolibriHttpClient('', fetcher as typeof fetch).cancelResponse('response-9');

    const requestInit = requestInits[0];
    expect(new Headers(requestInit?.headers).get('Idempotency-Key')).toBeTruthy();
    expect(JSON.parse(String(requestInit?.body))).toEqual({});
  });

  it('rejects unbound or unsafe artifact placeholders', () => {
    expect(normalizeVerifiedArtifact({ id: 'fake', name: 'fake.png' })).toBeNull();
    expect(
      normalizeVerifiedArtifact({
        id: 'bad',
        name: 'bad.png',
        mime_type: 'image/png',
        size_bytes: 10,
        sha256: 'a'.repeat(64),
        download_url: 'data:image/png;base64,AAAA',
      }),
    ).toBeNull();
  });

  it('accepts canonical edge artifact aliases only with a same-origin locator', () => {
    const artifact = normalizeVerifiedArtifact({
      id: 'artifact-edge',
      name: 'edge.pdf',
      media_type: 'application/pdf',
      size_bytes: 25,
      content_sha256: 'c'.repeat(64),
      locator: '/v1/artifacts/artifact-edge/content',
    });
    expect(artifact).toEqual(expect.objectContaining({
      id: 'artifact-edge',
      mimeType: 'application/pdf',
      sha256: 'c'.repeat(64),
      downloadUrl: '/v1/artifacts/artifact-edge/content',
    }));
    expect(normalizeVerifiedArtifact({
      id: 'bad-edge',
      name: 'bad.pdf',
      media_type: 'application/pdf',
      size_bytes: 25,
      content_sha256: 'c'.repeat(64),
      locator: 'https://external.example/artifact',
    })).toBeNull();
  });

  it('admits an estimate workspace only when every typed line is valid and artifact-bound', () => {
    const estimate = normalizeVerifiedArtifact({
      id: 'estimate-1',
      name: 'estimate.pdf',
      media_type: 'application/pdf',
      size_bytes: 250,
      content_sha256: 'd'.repeat(64),
      locator: '/v1/artifacts/estimate-1/content',
      artifact_type: 'estimate',
      data: {
        title: 'Предварительная смета',
        location: 'Лениногорск',
        priced_at: '12.07.2026',
        status: 'verified',
        source_summary: 'Прайс-листы проверены',
        lines: [{
          id: 'line-1',
          title: 'Фундамент',
          unit: 'м³',
          quantity: 10,
          unit_price_rub: 8500,
          amount_rub: 85000,
        }],
      },
    });
    expect(estimate).toEqual(expect.objectContaining({
      kind: 'estimate',
      estimate: expect.objectContaining({
        title: 'Предварительная смета',
        lines: [expect.objectContaining({ unitPriceRub: 8500 })],
      }),
    }));

    expect(normalizeVerifiedArtifact({
      id: 'estimate-bad',
      name: 'estimate.pdf',
      media_type: 'application/pdf',
      size_bytes: 250,
      content_sha256: 'd'.repeat(64),
      locator: '/v1/artifacts/estimate-bad/content',
      artifact_type: 'estimate',
      data: { title: 'Смета', source_summary: 'Источник', lines: [{ title: 'Без цены' }] },
    })).toBeNull();
  });
});

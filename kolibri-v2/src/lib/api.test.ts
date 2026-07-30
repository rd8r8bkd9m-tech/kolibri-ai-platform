import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  auth,
  chat,
  ensureShellBootstrap,
  estimates,
  normalizeStreamEvent,
  projects,
  readEventStream,
  responses,
  resumeResponseAfterDisconnect,
  resetShellBootstrapForTests,
  resolveApiBase,
} from './api'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const bootstrapPayload = {
  session_id: 'session_1',
  session_type: 'anonymous' as const,
  restored: false,
  expires_at: null,
}

const projectPayload = {
  id: 'project_1',
  title: 'Новый проект',
  title_source: 'default' as const,
  status: 'active' as const,
  version: 1,
  message_count: 0,
  metadata: {},
  created_at: '2026-07-13T10:00:00Z',
  updated_at: '2026-07-13T10:00:00Z',
  last_message_at: null,
  deleted_at: null,
}

beforeEach(() => resetShellBootstrapForTests())

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('API base resolution', () => {
  it('uses the production API base without a browser canary pathname', () => {
    expect(resolveApiBase()).toBe('/api/v1')
    expect(resolveApiBase('/')).toBe('/api/v1')
    expect(resolveApiBase('/chat')).toBe('/api/v1')
    expect(resolveApiBase('/__canary-preview/release_1/')).toBe('/api/v1')
  })

  it('resolves paired canary API bases for valid canary pathnames', () => {
    const maxLengthReleaseId = 'a'.repeat(160)

    expect(resolveApiBase('/__canary/release_1.2:3-/')).toBe('/__canary/release_1.2:3-/api/v1')
    expect(resolveApiBase('/__canary/A/app/path')).toBe('/__canary/A/api/v1')
    expect(resolveApiBase(`/__canary/${maxLengthReleaseId}/`)).toBe(`/__canary/${maxLengthReleaseId}/api/v1`)
  })

  it('rejects malformed, traversal, double-slash and too-long canary pathnames', () => {
    const malformedPathnames = [
      '/__canary/',
      '/__canary/release_1',
      '/__canary//release_1/',
      '/__canary/release_1//app',
      '/__canary/.release_1/',
      '/__canary/release id/',
      '/__canary/../app/',
      '/__canary/release_1/../app',
      '/__canary/release_1/%2e%2e/app',
      `/__canary/${'a'.repeat(161)}/`,
    ]

    for (const pathname of malformedPathnames) {
      expect(resolveApiBase(pathname)).toBe('/api/v1')
    }
  })

  it('computes module API URLs from the browser pathname', async () => {
    vi.resetModules()
    vi.stubGlobal('window', { location: { pathname: '/__canary/release_1/' } })

    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(bootstrapPayload))
    vi.stubGlobal('fetch', fetchMock)

    const api = await import('./api')

    await api.ensureShellBootstrap()

    expect(fetchMock).toHaveBeenCalledWith('/__canary/release_1/api/v1/shell/bootstrap', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
    }))
    expect(api.estimates.pdfUrl('estimate_1', 4)).toBe('/__canary/release_1/api/v1/estimates/estimate_1/pdf?version=4')
  })
})

describe('shell bootstrap and durable project API', () => {
  it('probes an anonymous browser session without treating it as an API error', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      authenticated: false,
      user: null,
    }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(auth.session()).resolves.toEqual({
      authenticated: false,
      user: null,
    })
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/session', expect.objectContaining({
      credentials: 'include',
    }))
  })

  it('single-flights bootstrap and always includes browser credentials', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(bootstrapPayload))
    vi.stubGlobal('fetch', fetchMock)

    const [first, second] = await Promise.all([ensureShellBootstrap(), ensureShellBootstrap()])

    expect(first.session_id).toBe('session_1')
    expect(second).toEqual(first)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/shell/bootstrap', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
    }))
  })

  it('recovers shell bootstrap from a transient mobile network interruption', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new TypeError('Load failed'))
      .mockResolvedValueOnce(jsonResponse(bootstrapPayload))
    vi.stubGlobal('fetch', fetchMock)

    const bootstrap = ensureShellBootstrap()
    await vi.advanceTimersByTimeAsync(300)

    await expect(bootstrap).resolves.toEqual(bootstrapPayload)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    vi.useRealTimers()
  })

  it('bootstraps once before listing projects and sends credentials on both calls', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(bootstrapPayload))
      .mockResolvedValueOnce(jsonResponse({ items: [projectPayload], total: 1, page: 1, page_size: 100 }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await projects.list({ page_size: 100 })

    expect(result.items[0]?.id).toBe('project_1')
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/shell/bootstrap')
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/projects?page_size=100')
    expect(fetchMock.mock.calls.every(call => (call[1] as RequestInit).credentials === 'include')).toBe(true)
  })

  it('renews an expired shell bootstrap once after a 428 project response', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(bootstrapPayload))
      .mockResolvedValueOnce(jsonResponse({ detail: { code: 'public_session_required', message: 'Session expired' } }, 428))
      .mockResolvedValueOnce(jsonResponse({ ...bootstrapPayload, restored: true }))
      .mockResolvedValueOnce(jsonResponse(projectPayload))
    vi.stubGlobal('fetch', fetchMock)

    await expect(projects.get('project_1')).resolves.toMatchObject({ id: 'project_1' })
    expect(fetchMock.mock.calls.map(call => call[0])).toEqual([
      '/api/v1/shell/bootstrap',
      '/api/v1/projects/project_1',
      '/api/v1/shell/bootstrap',
      '/api/v1/projects/project_1',
    ])
  })

  it('uses typed message routes and idempotency headers for append and lifecycle patch', async () => {
    const message = {
      id: 'message_1',
      project_id: 'project_1',
      sequence: 1,
      version: 1,
      role: 'assistant' as const,
      content: '',
      status: 'pending' as const,
      metadata: {},
      created_at: '2026-07-13T10:00:00Z',
      updated_at: '2026-07-13T10:00:00Z',
    }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(bootstrapPayload))
      .mockResolvedValueOnce(jsonResponse(message, 201))
      .mockResolvedValueOnce(jsonResponse({ ...message, version: 2, content: 'Готово', status: 'completed' }))
    vi.stubGlobal('fetch', fetchMock)

    await projects.appendMessage('project_1', {
      role: 'assistant',
      content: '',
      status: 'pending',
      client_message_id: 'local_1',
    }, 'message:local_1')
    await projects.updateMessage('project_1', 'message_1', {
      content: 'Готово',
      status: 'completed',
      metadata: { response_id: 'resp_kolibri_1' },
    }, 'assistant:message_1:completed:1')

    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/projects/project_1/messages')
    expect(fetchMock.mock.calls[1]?.[1]).toEqual(expect.objectContaining({
      method: 'POST',
      credentials: 'include',
      headers: expect.objectContaining({ 'Idempotency-Key': 'message:local_1' }),
    }))
    expect(fetchMock.mock.calls[2]?.[0]).toBe('/api/v1/projects/project_1/messages/message_1')
    expect(fetchMock.mock.calls[2]?.[1]).toEqual(expect.objectContaining({
      method: 'PATCH',
      credentials: 'include',
      headers: expect.objectContaining({ 'Idempotency-Key': 'assistant:message_1:completed:1' }),
    }))
  })

  it('redeems a project handoff only after browser bootstrap', async () => {
    const token = 'A'.repeat(43)
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(bootstrapPayload))
      .mockResolvedValueOnce(jsonResponse(projectPayload))
    vi.stubGlobal('fetch', fetchMock)

    await expect(projects.claim('project_1', token)).resolves.toMatchObject({ id: 'project_1' })

    expect(fetchMock.mock.calls.map(call => call[0])).toEqual([
      '/api/v1/shell/bootstrap',
      '/api/v1/projects/project_1/claim',
    ])
    expect(fetchMock.mock.calls[1]?.[1]).toEqual(expect.objectContaining({
      method: 'POST',
      credentials: 'include',
      body: JSON.stringify({ token }),
    }))
  })
})

describe('safe response stream', () => {
  it('resumes from zero once, then continues after the last canonical sequence', async () => {
    const cursors: number[] = []
    const replayed: number[] = []
    const resume = vi.spyOn(responses, 'resume')
    resume.mockImplementationOnce(async (_id, startingAfter, onEvent) => {
      cursors.push(startingAfter)
      onEvent({ type: 'response.output_text.delta', response_id: 'resp_1', sequence: 1, content: 'A', done: false })
      onEvent({ type: 'response.output_text.delta', response_id: 'resp_1', sequence: 2, content: 'B', done: false })
      throw new Error('peer closed connection')
    })
    resume.mockImplementationOnce(async (_id, startingAfter, onEvent) => {
      cursors.push(startingAfter)
      onEvent({ type: 'response.output_text.delta', response_id: 'resp_1', sequence: 2, content: 'B', done: false })
      const terminal = { type: 'response.completed', response_id: 'resp_1', sequence: 3, done: true } as const
      onEvent(terminal)
      return terminal
    })

    const terminal = await resumeResponseAfterDisconnect(
      'resp_1',
      event => { if (event.sequence !== undefined) replayed.push(event.sequence) },
      { retryDelayMs: 0 },
    )

    expect(cursors).toEqual([0, 2])
    expect(replayed).toEqual([1, 2, 3])
    expect(terminal).toMatchObject({ sequence: 3, done: true })
  })

  it('normalizes output deltas and terminal events', () => {
    expect(normalizeStreamEvent({
      event: 'response.output_text.delta',
      id: '7',
      data: JSON.stringify({ type: 'response.output_text.delta', response_id: 'resp_1', sequence: 7, delta: 'Привет' }),
    })).toMatchObject({
      type: 'response.output_text.delta',
      response_id: 'resp_1',
      sequence: 7,
      content: 'Привет',
      done: false,
    })

    expect(normalizeStreamEvent({
      data: JSON.stringify({ type: 'response.completed', response: { id: 'resp_1' } }),
    })).toMatchObject({ response_id: 'resp_1', status: 'completed', done: true })
  })

  it('never treats a legacy durable handoff as a terminal response', () => {
    expect(normalizeStreamEvent({
      data: JSON.stringify({
        content: '',
        done: true,
        status: 'queued',
        response_id: 'resp_background_legacy',
      }),
    })).toMatchObject({
      response_id: 'resp_background_legacy',
      status: 'queued',
      done: false,
    })
  })

  it('continues a clean background handoff from its canonical sequence', async () => {
    const initialStream = [
      'event: response.created',
      'data: {"type":"response.created","response":{"id":"resp_background_1","status":"in_progress"}}',
      '',
      'event: response.status.updated',
      'id: 2',
      'data: {"type":"response.status.updated","response_id":"resp_background_1","sequence":2,"status":"queued","response":{"id":"resp_background_1","status":"queued"}}',
      '',
      '',
    ].join('\n')
    const replayStream = [
      'event: response.output_text.delta',
      'id: 3',
      'data: {"type":"response.output_text.delta","response_id":"resp_background_1","sequence":3,"delta":"Фоновый ответ готов"}',
      '',
      'event: response.completed',
      'id: 4',
      'data: {"type":"response.completed","response_id":"resp_background_1","sequence":4,"response":{"id":"resp_background_1","status":"completed"}}',
      '',
      '',
    ].join('\n')
    const eventStream = (body: string) => new Response(body, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    })
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(eventStream(initialStream))
      .mockResolvedValueOnce(eventStream(replayStream))
    vi.stubGlobal('fetch', fetchMock)
    const received: Array<ReturnType<typeof normalizeStreamEvent>> = []

    const terminal = await chat.stream(
      [{ role: 'user', content: 'Долгая задача' }],
      event => received.push(event),
      undefined,
      {
        policy: {
          mode: 'deep',
          reasoning_effort: 'high',
          tool_choice: 'auto',
          background: true,
          allowed_capabilities: [],
        },
      },
    )

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      '/api/v1/responses/resp_background_1/events?starting_after=2',
    )
    expect(received.filter(event => event?.content).map(event => event?.content)).toEqual([
      'Фоновый ответ готов',
    ])
    expect(terminal).toMatchObject({
      type: 'response.completed',
      response_id: 'resp_background_1',
      sequence: 4,
      done: true,
    })
  })

  it('deduplicates a legacy image text chunk while retaining canonical sequences', async () => {
    const artifactId = '11111111-1111-4111-8111-111111111111'
    const stream = [
      'data: {"type":"response.created","response":{"id":"resp_image_1","status":"in_progress"}}',
      '',
      'data: {"content":"Изображение создано.","done":false}',
      '',
      'data: {"type":"response.output_text.delta","response_id":"resp_image_1","sequence":5,"delta":"Изображение создано."}',
      '',
      `data: {"type":"response.artifact.ready","response_id":"resp_image_1","sequence":6,"artifact_type":"image","artifact_id":"${artifactId}","artifact":{"id":"${artifactId}","type":"image"}}`,
      '',
      'data: {"type":"response.completed","response_id":"resp_image_1","sequence":7,"response":{"id":"resp_image_1","status":"completed"}}',
      '',
      'data: {"content":"","done":true,"status":"ready","provider":"kolibri","model":"kolibri"}',
      '',
      '',
    ].join('\n')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(stream, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    })))
    const received: Array<ReturnType<typeof normalizeStreamEvent>> = []

    const terminal = await chat.stream(
      [{ role: 'user', content: 'Создай изображение' }],
      event => received.push(event),
    )

    expect(received.filter(event => event?.content).map(event => event?.content)).toEqual([
      'Изображение создано.',
    ])
    expect(received.filter(event => event?.sequence).map(event => event?.sequence)).toEqual([5, 6, 7])
    expect(terminal).toMatchObject({ done: true, status: 'ready' })
  })

  it('deduplicates a legacy text chunk emitted after its canonical delta', async () => {
    const stream = [
      'data: {"type":"response.created","response":{"id":"resp_text_1","status":"in_progress"}}',
      '',
      'data: {"type":"response.output_text.delta","response_id":"resp_text_1","sequence":2,"delta":"Привет"}',
      '',
      'data: {"content":"Привет","done":false}',
      '',
      'data: {"type":"response.completed","response_id":"resp_text_1","sequence":3,"response":{"id":"resp_text_1","status":"completed"}}',
      '',
      'data: {"content":"","done":true,"status":"ready","provider":"kolibri","model":"kolibri"}',
      '',
      '',
    ].join('\n')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(stream, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    })))
    const received: Array<ReturnType<typeof normalizeStreamEvent>> = []

    const terminal = await chat.stream(
      [{ role: 'user', content: 'Привет' }],
      event => received.push(event),
    )

    expect(received.filter(event => event?.content).map(event => event?.content)).toEqual([
      'Привет',
    ])
    expect(received.filter(event => event?.sequence).map(event => event?.sequence)).toEqual([2, 3])
    expect(terminal).toMatchObject({ done: true, status: 'ready' })
  })

  it('normalizes the canonical nested reasoning excerpt without private fields', () => {
    expect(normalizeStreamEvent({
      event: 'response.work_summary.updated',
      id: '17',
      data: JSON.stringify({
        type: 'response.work_summary.updated',
        response_id: 'resp_1',
        sequence: 17,
        work_summary: {
          kind: 'reasoning_excerpt',
          summary_id: 'summary_1',
          step_id: 'step_1',
          stage: 'reasoning_summary',
          status: 'active',
          summary: 'Сверяю цены по региону объекта',
          occurred_at: '2026-07-14T12:00:00Z',
          provider: 'private-provider',
          model: 'private-model',
          reasoning_content: 'must not escape',
          tool_arguments: { secret: true },
        },
      }),
    })).toEqual({
      type: 'response.work_summary.updated',
      response_id: 'resp_1',
      sequence: 17,
      content: undefined,
      done: false,
      status: undefined,
      error_code: undefined,
      recoverable: false,
      capability: undefined,
      actions: undefined,
      work_summary: {
        kind: 'reasoning_excerpt',
        summary_id: 'summary_1',
        step_id: 'step_1',
        stage: 'reasoning_summary',
        status: 'active',
        summary: 'Сверяю цены по региону объекта',
        occurred_at: '2026-07-14T12:00:00Z',
        response_id: 'resp_1',
        sequence: 17,
        artifact_type: undefined,
        artifact_id: undefined,
      },
    })
  })

  it('keeps the typed image artifact action for byte verification after streaming', () => {
    const artifact = {
      id: '11111111-1111-4111-8111-111111111111',
      type: 'image',
      revision: 1,
      title: 'Цветы',
      prompt: 'сгенерируй цветы',
      mime_type: 'image/png',
      size_bytes: 2048,
      sha256: 'a'.repeat(64),
      model: 'codex-cli:account-default',
      created_at: '2026-07-14T10:00:00Z',
      updated_at: '2026-07-14T10:00:01Z',
      url: '/api/v1/artifacts/images/11111111-1111-4111-8111-111111111111',
      download_url: '/api/v1/artifacts/images/11111111-1111-4111-8111-111111111111?download=true',
      revision_url: '/api/v1/artifacts/11111111-1111-4111-8111-111111111111?revision=1',
      revision_download_url: '/api/v1/artifacts/11111111-1111-4111-8111-111111111111?revision=1&download=true',
      reopen_url: '/api/v1/artifacts/11111111-1111-4111-8111-111111111111/reopen',
      history_url: '/api/v1/artifacts/11111111-1111-4111-8111-111111111111/history',
    }
    expect(normalizeStreamEvent({
      event: 'response.artifact.ready',
      data: JSON.stringify({
        type: 'response.artifact.ready',
        response_id: 'resp_image_1',
        artifact_type: 'image',
        artifact_id: artifact.id,
        artifact,
      }),
    })).toMatchObject({
      type: 'response.artifact.ready',
      response_id: 'resp_image_1',
      actions: [{ type: 'present_image', data: artifact }],
      work_summary: { stage: 'artifact_verification', artifact_type: 'image', artifact_id: artifact.id },
    })
  })

  it('keeps non-image artifact manifests for the same fail-closed byte verification path', () => {
    const artifact = {
      id: '33333333-3333-4333-8333-333333333333',
      type: 'document.pdf',
      title: 'Отчёт',
    }
    expect(normalizeStreamEvent({
      event: 'response.artifact.ready',
      data: JSON.stringify({
        type: 'response.artifact.ready',
        response_id: 'resp_pdf_1',
        artifact_type: 'document.pdf',
        artifact_id: artifact.id,
        artifact,
      }),
    })).toMatchObject({
      actions: [{ type: 'present_artifact', data: artifact }],
      work_summary: { artifact_type: 'document.pdf', artifact_id: artifact.id },
    })
  })

  it('exposes only sanitized provider failure facts', () => {
    expect(normalizeStreamEvent({
      data: JSON.stringify({
        type: 'provider.attempt.failed',
        provider: 'mimo',
        model: 'mimo-code',
        failure_kind: 'timeout',
        will_retry: true,
        prompt: 'must not be copied into the public event',
      }),
    })).toEqual({
      type: 'provider.attempt.failed',
      response_id: undefined,
      sequence: undefined,
      provider_event: {
        type: 'provider.attempt.failed',
        provider: 'mimo',
        model: 'mimo-code',
        failure_kind: 'timeout',
        will_retry: true,
      },
    })
  })

  it('drops unsupported work-trace stages and private legacy fields', () => {
    expect(normalizeStreamEvent({
      data: JSON.stringify({
        content: 'Готово',
        reasoning: 'private reasoning must not survive normalization',
        work_summary: {
          stage: 'private_chain_of_thought',
          status: 'active',
          summary: 'hidden detail',
        },
      }),
    })).toEqual({
      content: 'Готово',
      done: false,
      status: undefined,
      error_code: undefined,
      recoverable: false,
      capability: undefined,
      actions: undefined,
      provider: undefined,
      model: undefined,
      fallback_used: false,
      work_summary: undefined,
      provider_event: undefined,
      response_id: undefined,
      sequence: undefined,
    })
  })

  it('maps backend-only work-trace aliases into the canonical public contract', () => {
    expect(normalizeStreamEvent({
      event: 'response.work_summary.updated',
      data: JSON.stringify({
        type: 'response.work_summary.updated',
        response_id: 'resp_alias',
        sequence: 18,
        work_summary: {
          stage: 'factory_dispatch',
          status: 'waiting',
          summary: 'Передаю в Home Control Plane',
        },
      }),
    })?.work_summary).toMatchObject({
      stage: 'provider_route',
      status: 'active',
      response_id: 'resp_alias',
      sequence: 18,
    })

    expect(normalizeStreamEvent({
      data: JSON.stringify({
        work_summary: {
          stage: 'codex_turn',
          status: 'recovering',
          summary: 'Codex продолжает выполнение',
        },
      }),
    })?.work_summary).toMatchObject({
      stage: 'tool_execution',
      status: 'active',
    })

    expect(normalizeStreamEvent({
      data: JSON.stringify({
        work_summary: {
          stage: 'plan_updated',
          status: 'cancelled',
          summary: 'План остановлен',
        },
      }),
    })?.work_summary).toMatchObject({
      stage: 'planning',
      status: 'failed',
    })
  })

  it('preserves only the structured recoverable capability error', () => {
    expect(normalizeStreamEvent({
      event: 'response.failed',
      data: JSON.stringify({
        type: 'response.failed',
        response: {
          id: 'resp_image_1',
          error: {
            code: 'capability_unavailable',
            capability: 'image.generate',
            recoverable: true,
            private_provider_error: 'must not escape',
          },
        },
      }),
    })).toMatchObject({
      type: 'response.failed',
      response_id: 'resp_image_1',
      status: 'failed',
      done: true,
      error_code: 'capability_unavailable',
      capability: 'image.generate',
      recoverable: true,
    })
  })

  it('parses fragmented, multiline SSE frames', async () => {
    const encoder = new TextEncoder()
    const chunks = [
      'event: response.output_text.delta\nid: 1\ndata: {"type":"response.output_text.delta",',
      '"delta":"A"}\n\nevent: response.completed\ndata: {"type":"response.completed",\n',
      'data: "response_id":"resp_1"}\n\n',
    ]
    const response = new Response(new ReadableStream({
      start(controller) {
        chunks.forEach(chunk => controller.enqueue(encoder.encode(chunk)))
        controller.close()
      },
    }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
    const handler = vi.fn()
    await readEventStream(response, handler)
    expect(handler).toHaveBeenCalledTimes(2)
    expect(handler.mock.calls[0]?.[0]).toMatchObject({ event: 'response.output_text.delta', id: '1' })
    expect(handler.mock.calls[1]?.[0].data).toBe('{"type":"response.completed",\n"response_id":"resp_1"}')
  })
})

describe('revision-backed estimate artifacts', () => {
  it('builds immutable revision export URLs for PDF, XLSX and JSON', () => {
    expect(estimates.pdfUrl('estimate_1', 4)).toBe('/api/v1/estimates/estimate_1/pdf?version=4')
    expect(estimates.exportUrl('estimate_1', 'xlsx', 4)).toBe('/api/v1/estimates/estimate_1/export/xlsx?version=4')
    expect(estimates.exportUrl('estimate_1', 'json', 2)).toBe('/api/v1/estimates/estimate_1/export/json?version=2')
  })
})

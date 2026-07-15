import { describe, expect, it, vi } from 'vitest'
import type { ConversationArtifact } from '@/features/conversation/ArtifactCard'
import type { ChatAction, Estimate, FileArtifact, ImageArtifact } from '@/lib/api'
import {
  buildPersistedConversationMetadata,
  hydratePersistedArtifact,
  normalizePersistedAction,
  restoreConversationMetadata,
} from './persistedConversation'

const image: ImageArtifact = {
  id: '11111111-1111-4111-8111-111111111111',
  type: 'image',
  revision: 1,
  title: 'Цветы',
  prompt: 'Букет полевых цветов',
  mime_type: 'image/png',
  size_bytes: 2048,
  sha256: 'a'.repeat(64),
  model: 'gpt-image-1',
  created_at: '2026-07-13T13:00:00Z',
  updated_at: '2026-07-13T13:00:01Z',
  url: '/api/v1/artifacts/images/11111111-1111-4111-8111-111111111111',
  download_url: '/api/v1/artifacts/images/11111111-1111-4111-8111-111111111111?download=true',
  revision_url: '/api/v1/artifacts/11111111-1111-4111-8111-111111111111?revision=1',
  revision_download_url: '/api/v1/artifacts/11111111-1111-4111-8111-111111111111?revision=1&download=true',
  reopen_url: '/api/v1/artifacts/11111111-1111-4111-8111-111111111111/reopen',
  history_url: '/api/v1/artifacts/11111111-1111-4111-8111-111111111111/history',
}

const estimate: Estimate = {
  id: '22222222-2222-4222-8222-222222222222',
  version: 3,
  status: 'ready',
  title: 'Смета: дом 100 м²',
  client: '',
  object_name: 'Дом',
  region: 'Лениногорск',
  currency: 'RUB',
  overhead_rate: '0',
  vat_rate: '22',
  subtotal: '1000',
  overhead_amount: '0',
  vat_amount: '220',
  total: '1220',
  sections: [],
  created_at: '2026-07-13T13:00:00Z',
  updated_at: '2026-07-13T13:01:00Z',
}

const file: FileArtifact = {
  id: '33333333-3333-4333-8333-333333333333',
  type: 'document.pdf', revision: 1, title: 'Отчёт', filename: 'report.pdf', mime_type: 'application/pdf',
  size_bytes: 4096, sha256: 'b'.repeat(64), created_at: '2026-07-14T10:00:00Z', updated_at: '2026-07-14T10:00:01Z', metadata: {},
  url: '/api/v1/artifacts/33333333-3333-4333-8333-333333333333',
  download_url: '/api/v1/artifacts/33333333-3333-4333-8333-333333333333?download=true',
  revision_url: '/api/v1/artifacts/33333333-3333-4333-8333-333333333333?revision=1',
  revision_download_url: '/api/v1/artifacts/33333333-3333-4333-8333-333333333333?revision=1&download=true',
  reopen_url: '/api/v1/artifacts/33333333-3333-4333-8333-333333333333/reopen',
  history_url: '/api/v1/artifacts/33333333-3333-4333-8333-333333333333/history',
}

describe('persisted conversation artifacts', () => {
  it('persists the canonical reasoning excerpt for reload without private fields', () => {
    const metadata = buildPersistedConversationMetadata({
      responseId: 'resp_1',
      workEvents: [{
        kind: 'reasoning_excerpt',
        summary_id: 'summary_1',
        step_id: 'step_1',
        stage: 'reasoning_summary',
        status: 'completed',
        summary: 'Сопоставляю работы с технологической картой',
        occurred_at: '2026-07-14T12:00:00Z',
        response_id: 'resp_1',
        sequence: 17,
      }],
    })

    expect(restoreConversationMetadata(metadata)).toMatchObject({
      responseId: 'resp_1',
      workEvents: [{
        kind: 'reasoning_excerpt',
        summary_id: 'summary_1',
        stage: 'reasoning_summary',
        status: 'completed',
      }],
    })
    expect(metadata).toMatchObject({ response_id: 'resp_1' })
    expect(metadata.work_events).toEqual([
      expect.not.objectContaining({ response_id: expect.anything() }),
    ])
    expect(metadata.work_events).toEqual([
      expect.not.objectContaining({ sequence: expect.anything() }),
    ])
    expect(JSON.stringify(metadata)).not.toContain('reasoning_content')
  })

  it('normalizes backend work-trace aliases before persisting history', () => {
    const metadata = buildPersistedConversationMetadata({
      responseId: 'resp_alias',
      workEvents: [
        {
          stage: 'factory_dispatch' as never,
          status: 'waiting' as never,
          summary: 'Передаю в Home Control Plane',
        },
        {
          stage: 'codex_turn' as never,
          status: 'recovering' as never,
          summary: 'Codex выполняет шаг',
        },
      ],
    })

    expect(restoreConversationMetadata(metadata).workEvents).toMatchObject([
      { stage: 'provider_route', status: 'active' },
      { stage: 'tool_execution', status: 'active' },
    ])
  })

  it('persists and restores the exact verified image URL and hash', async () => {
    const artifact: ConversationArtifact = { type: 'image', value: image }
    const metadata = buildPersistedConversationMetadata({
      responseId: 'resp_kolibri_image_1',
      workEvents: [{ stage: 'artifact_verification', status: 'completed', summary: 'Файл проверен', artifact_type: 'image', artifact_id: image.id }],
      artifact,
    })

    const restored = restoreConversationMetadata(metadata)
    expect(restored.actions).toEqual([])
    expect(restored.artifact).toMatchObject({
      type: 'image',
      value: {
        url: image.url,
        download_url: image.download_url,
        revision_url: image.revision_url,
        reopen_url: image.reopen_url,
        sha256: image.sha256,
      },
    })
    const hydrated = await hydratePersistedArtifact(restored.artifact!, {
      estimate: vi.fn(),
      document: vi.fn(),
    })
    expect(hydrated).toEqual(artifact)
  })

  it('stores only an immutable estimate reference and reloads the same card', async () => {
    const metadata = buildPersistedConversationMetadata({ artifact: { type: 'estimate', value: estimate } })
    expect(metadata.artifact).toEqual({
      type: 'estimate',
      id: estimate.id,
      version: 3,
      title: estimate.title,
    })
    const restored = restoreConversationMetadata(metadata)
    const estimateLoader = vi.fn().mockResolvedValue(estimate)
    const hydrated = await hydratePersistedArtifact(restored.artifact!, {
      estimate: estimateLoader,
      document: vi.fn(),
    })
    expect(estimateLoader).toHaveBeenCalledWith(estimate.id)
    expect(hydrated).toEqual({ type: 'estimate', value: estimate })
  })

  it('persists the immutable file manifest without its runtime object URL', async () => {
    const runtimeFile = { ...file, object_url: 'blob:must-not-persist' }
    const metadata = buildPersistedConversationMetadata({
      artifact: { type: 'file', value: runtimeFile },
    })
    expect(JSON.stringify(metadata)).not.toContain('blob:must-not-persist')
    const restored = restoreConversationMetadata(metadata)
    expect(restored.artifact).toEqual({ type: 'file', value: file })
    await expect(hydratePersistedArtifact(restored.artifact!, {
      estimate: vi.fn(),
      document: vi.fn(),
    })).resolves.toEqual({ type: 'file', value: file })
  })

  it('never restores fake image actions or executable actions beside a materialized artifact', () => {
    const validEstimateAction: ChatAction = {
      type: 'create_estimate',
      label: 'Открыть смету',
      data: {
        title: 'Смета',
        sections: [{ title: 'Работы', positions: [{ code: '', name: 'Монтаж', unit: 'шт', quantity: '1', price: '100', source: '', comment: '' }] }],
      },
    }
    const withArtifact = buildPersistedConversationMetadata({
      actions: [validEstimateAction],
      artifact: { type: 'image', value: image },
    })
    expect(withArtifact.actions).toBeUndefined()

    const restored = restoreConversationMetadata({
      actions: [
        validEstimateAction,
        {
          type: 'present_image',
          label: 'Поддельное изображение',
          data: { ...image, url: 'https://attacker.invalid/fake.png' },
        },
        { type: 'unknown', label: 'Неизвестно', data: {} },
      ],
    })
    expect(restored.actions).toHaveLength(1)
    expect(restored.actions[0]).toMatchObject({
      ...validEstimateAction,
      label: 'Открыть предварительную смету',
    })
  })

  it('rejects stale or inconsistent estimate references during hydration', async () => {
    const restored = restoreConversationMetadata(buildPersistedConversationMetadata({
      artifact: { type: 'estimate', value: estimate },
    }))
    await expect(hydratePersistedArtifact(restored.artifact!, {
      estimate: vi.fn().mockResolvedValue({ ...estimate, version: 2 }),
      document: vi.fn(),
    })).rejects.toThrow('stale or inconsistent')
  })

  it('preserves attested evidence for materialization but never trusts browser truth promotion', () => {
    const action = normalizePersistedAction({
      type: 'create_estimate',
      label: 'Открыть смету',
      data: {
        title: 'Смета: дом',
        region: 'Лениногорск, Татарстан',
        estimate_status: 'verified',
        pricing_status: 'verified',
        scope_status: 'verified',
        assumptions: ['Площадь принята по проекту'],
        questions: ['Подтвердите сроки поставки'],
        source_note: 'Цены проверены по региональным источникам.',
        price_sources: [{
          position_code: 'М-1',
          source_id: 'source-1',
          url: 'https://supplier.example/material',
          source_title: 'Прайс поставщика',
          source_type: 'supplier_quote',
          region: 'Татарстан',
          observed_at: '2026-07-14T07:00:00Z',
          price_date: '2026-07-14',
          unit: 'шт',
          unit_price: '100',
          vat_status: 'included',
          quote: 'Материал — 100 ₽/шт с НДС',
          currency: 'RUB',
          content_sha256: 'a'.repeat(64),
          verification: 'verified',
          attestation: 'b'.repeat(64),
        }],
        sections: [{
          title: 'Материалы',
          positions: [{
            code: 'М-1', name: 'Материал', unit: 'шт', quantity: '1', price: '100', source: '', comment: '',
            source_evidence: {
              position_code: 'М-1',
              source_id: 'source-1',
              url: 'https://supplier.example/material',
              source_title: 'Прайс поставщика',
              source_type: 'supplier_quote',
              region: 'Татарстан',
              observed_at: '2026-07-14T07:00:00Z',
              price_date: '2026-07-14',
              unit: 'шт',
              unit_price: '100',
              vat_status: 'included',
              quote: 'Материал — 100 ₽/шт с НДС',
              currency: 'RUB',
              content_sha256: 'a'.repeat(64),
              verification: 'verified',
              attestation: 'b'.repeat(64),
            },
          }],
        }],
      },
    })

    expect(action).toMatchObject({
      label: 'Открыть предварительную смету',
      data: {
        estimate_status: 'preliminary',
        pricing_status: 'preliminary',
        scope_status: 'unverified',
        assumptions: ['Площадь принята по проекту'],
        questions: ['Подтвердите сроки поставки'],
        price_sources: [{ source_id: 'source-1', verification: 'verified', attestation: 'b'.repeat(64) }],
        sections: [{ positions: [{ price_evidence: [{ source_id: 'source-1', verification: 'verified', attestation: 'b'.repeat(64) }] }] }],
      },
    })
  })

  it('downgrades source evidence when the trusted collector attestation is missing', () => {
    const action = normalizePersistedAction({
      type: 'create_estimate',
      label: 'Открыть смету',
      data: {
        title: 'Смета',
        estimate_status: 'source_backed',
        pricing_status: 'source_backed',
        price_sources: [{
          position_code: 'М-1', source_id: 'source-1', url: 'https://supplier.example/material',
          source_title: 'Прайс', source_type: 'supplier_quote', region: 'Татарстан',
          observed_at: '2026-07-14T07:00:00Z', price_date: '2026-07-14', unit: 'шт',
          unit_price: '100', vat_status: 'included', quote: '100 ₽/шт', currency: 'RUB',
          content_sha256: 'a'.repeat(64), verification: 'verified',
        }],
        sections: [{
          title: 'Материалы',
          positions: [{ code: 'М-1', name: 'Материал', unit: 'шт', quantity: '1', price: '100' }],
        }],
      },
    })

    expect(action).toMatchObject({
      label: 'Открыть предварительную смету',
      data: {
        estimate_status: 'preliminary',
        pricing_status: 'preliminary',
        scope_status: 'unverified',
        price_sources: [],
        sections: [{ positions: [{ price_evidence: [] }] }],
      },
    })
  })
})

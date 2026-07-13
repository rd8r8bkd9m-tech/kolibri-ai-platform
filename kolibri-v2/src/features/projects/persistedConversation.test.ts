import { describe, expect, it, vi } from 'vitest'
import type { ConversationArtifact } from '@/features/conversation/ArtifactCard'
import type { ChatAction, Estimate, ImageArtifact } from '@/lib/api'
import {
  buildPersistedConversationMetadata,
  hydratePersistedArtifact,
  restoreConversationMetadata,
} from './persistedConversation'

const image: ImageArtifact = {
  id: '11111111-1111-4111-8111-111111111111',
  type: 'image',
  title: 'Цветы',
  prompt: 'Букет полевых цветов',
  mime_type: 'image/png',
  size_bytes: 2048,
  sha256: 'a'.repeat(64),
  model: 'gpt-image-1',
  created_at: '2026-07-13T13:00:00Z',
  url: '/api/v1/artifacts/images/11111111-1111-4111-8111-111111111111',
  download_url: '/api/v1/artifacts/images/11111111-1111-4111-8111-111111111111?download=true',
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

describe('persisted conversation artifacts', () => {
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
      value: { url: image.url, download_url: image.download_url, sha256: image.sha256 },
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
    expect(restored.actions[0]).toMatchObject(validEstimateAction)
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
})

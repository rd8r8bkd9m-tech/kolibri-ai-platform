import { describe, expect, it } from 'vitest'
import { normalizeImageArtifact } from './imageArtifact'

const artifact = {
  id: 'c1c4425b-b4ee-4bb9-83dc-2f78053c4348',
  type: 'image',
  title: 'Цветы',
  prompt: 'сгенерируй цветы',
  mime_type: 'image/png',
  size_bytes: 1024,
  sha256: 'a'.repeat(64),
  model: 'gpt-image-2',
  created_at: '2026-07-13T12:00:00+00:00',
  url: '/api/v1/artifacts/images/c1c4425b-b4ee-4bb9-83dc-2f78053c4348',
  download_url: '/api/v1/artifacts/images/c1c4425b-b4ee-4bb9-83dc-2f78053c4348?download=true',
}

describe('normalizeImageArtifact', () => {
  it('accepts the complete verified image contract', () => {
    expect(normalizeImageArtifact(artifact)).toEqual(artifact)
  })

  it.each([
    ['missing id', { id: '' }],
    ['wrong type', { type: 'text' }],
    ['non-image MIME', { mime_type: 'text/html' }],
    ['zero bytes', { size_bytes: 0 }],
    ['invalid digest', { sha256: 'fake' }],
    ['mismatched URL', { url: '/api/v1/artifacts/images/other' }],
    ['mismatched download URL', { download_url: '/api/v1/artifacts/images/other?download=true' }],
  ])('rejects %s', (_label, patch) => {
    expect(() => normalizeImageArtifact({ ...artifact, ...patch })).toThrow(
      'verified artifact contract',
    )
  })
})

import { createHash } from 'node:crypto'
import { describe, expect, it, vi } from 'vitest'
import {
  expectsImageArtifact,
  normalizeImageArtifact,
  safeContentBeforeImageVerification,
  verifyImageArtifact,
} from './imageArtifact'

const artifact = {
  id: 'c1c4425b-b4ee-4bb9-83dc-2f78053c4348',
  type: 'image',
  revision: 1,
  title: 'Цветы',
  prompt: 'сгенерируй цветы',
  mime_type: 'image/png',
  size_bytes: 1024,
  sha256: 'a'.repeat(64),
  model: 'gpt-image-2',
  created_at: '2026-07-13T12:00:00+00:00',
  updated_at: '2026-07-13T12:00:01+00:00',
  url: '/api/v1/artifacts/images/c1c4425b-b4ee-4bb9-83dc-2f78053c4348',
  download_url: '/api/v1/artifacts/images/c1c4425b-b4ee-4bb9-83dc-2f78053c4348?download=true',
  revision_url: '/api/v1/artifacts/c1c4425b-b4ee-4bb9-83dc-2f78053c4348?revision=1',
  revision_download_url: '/api/v1/artifacts/c1c4425b-b4ee-4bb9-83dc-2f78053c4348?revision=1&download=true',
  reopen_url: '/api/v1/artifacts/c1c4425b-b4ee-4bb9-83dc-2f78053c4348/reopen',
  history_url: '/api/v1/artifacts/c1c4425b-b4ee-4bb9-83dc-2f78053c4348/history',
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
    ['missing reopen URL', { reopen_url: '' }],
    ['mismatched revision URL', { revision_url: '/api/v1/artifacts/c1c4425b-b4ee-4bb9-83dc-2f78053c4348?revision=2' }],
  ])('rejects %s', (_label, patch) => {
    expect(() => normalizeImageArtifact({ ...artifact, ...patch })).toThrow(
      'verified artifact contract',
    )
  })
})

describe('verified image bytes boundary', () => {
  const pngBytes = Uint8Array.from(Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    'base64',
  ))
  const verifiedMetadata = {
    ...artifact,
    size_bytes: pngBytes.byteLength,
    sha256: createHash('sha256').update(pngBytes).digest('hex'),
  }

  it('returns a runtime object URL only after MIME, bytes, digest and decode pass', async () => {
    const decode = vi.fn().mockResolvedValue(undefined)
    const createObjectURL = vi.fn().mockReturnValue('blob:verified-flowers')
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(new Response(pngBytes, {
        status: 200,
        headers: { 'Content-Type': 'image/png' },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        revision: verifiedMetadata.revision,
        content_url: verifiedMetadata.revision_url,
        download_url: verifiedMetadata.revision_download_url,
        integrity: { algorithm: 'sha256', digest: verifiedMetadata.sha256 },
        artifact: { id: verifiedMetadata.id, type: 'image' },
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))

    await expect(verifyImageArtifact(verifiedMetadata, {
      fetchImpl,
      decode,
      createObjectURL,
    })).resolves.toEqual({ ...verifiedMetadata, object_url: 'blob:verified-flowers' })
    expect(fetchImpl).toHaveBeenNthCalledWith(1, verifiedMetadata.revision_url, expect.objectContaining({
      method: 'GET',
      credentials: 'include',
      cache: 'no-store',
    }))
    expect(fetchImpl).toHaveBeenNthCalledWith(2, verifiedMetadata.reopen_url, expect.objectContaining({
      method: 'GET',
      credentials: 'include',
      cache: 'no-store',
    }))
    expect(decode).toHaveBeenCalledOnce()
    expect(createObjectURL).toHaveBeenCalledOnce()
  })

  it.each([
    ['wrong MIME', new Response(pngBytes, { headers: { 'Content-Type': 'text/html' } })],
    ['missing bytes', new Response(new Uint8Array(), { headers: { 'Content-Type': 'image/png' } })],
    ['wrong raster signature', new Response(new Uint8Array(pngBytes.byteLength), { headers: { 'Content-Type': 'image/png' } })],
  ])('does not create a card URL for %s', async (_label, response) => {
    const createObjectURL = vi.fn().mockReturnValue('blob:must-not-exist')
    await expect(verifyImageArtifact(verifiedMetadata, {
      fetchImpl: vi.fn().mockResolvedValue(response),
      decode: vi.fn().mockResolvedValue(undefined),
      createObjectURL,
    })).rejects.toThrow()
    expect(createObjectURL).not.toHaveBeenCalled()
  })

  it('does not create a card URL when reopen is not bound to the verified revision', async () => {
    const createObjectURL = vi.fn().mockReturnValue('blob:must-not-exist')
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(new Response(pngBytes, {
        status: 200,
        headers: { 'Content-Type': 'image/png' },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        revision: verifiedMetadata.revision,
        content_url: verifiedMetadata.revision_url,
        download_url: verifiedMetadata.revision_download_url,
        integrity: { algorithm: 'sha256', digest: 'b'.repeat(64) },
        artifact: { id: verifiedMetadata.id, type: 'image' },
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))

    await expect(verifyImageArtifact(verifiedMetadata, {
      fetchImpl,
      decode: vi.fn().mockResolvedValue(undefined),
      createObjectURL,
    })).rejects.toThrow('reopen')
    expect(createObjectURL).not.toHaveBeenCalled()
  })
})

describe('image response copy gate', () => {
  it('treats the public flower prompt as an artifact request', () => {
    expect(expectsImageArtifact('сгенерируй цветы')).toBe(true)
    expect(expectsImageArtifact('Подготовь договор подряда')).toBe(false)
  })

  it('never shows a provider success claim before raster bytes are verified', () => {
    expect(safeContentBeforeImageVerification('Изображение создано.', false)).toBe('')
    expect(safeContentBeforeImageVerification('Генерирую файл…', true)).toBe('')
    expect(safeContentBeforeImageVerification('Обычный текстовый ответ', false)).toBe('Обычный текстовый ответ')
  })
})

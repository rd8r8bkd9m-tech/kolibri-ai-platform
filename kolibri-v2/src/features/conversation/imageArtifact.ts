import type { ImageArtifact } from '@/lib/api'

const IMAGE_MIME_TYPES = new Set<ImageArtifact['mime_type']>([
  'image/png',
  'image/jpeg',
  'image/webp',
])
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const SHA256 = /^[a-f0-9]{64}$/

/**
 * Fail closed before rendering an image action. The backend remains the byte
 * authority; this boundary prevents action-shaped provider text from becoming
 * a trusted image card in the Shell.
 */
export function normalizeImageArtifact(data: Record<string, unknown>): ImageArtifact {
  const id = String(data.id || '')
  const type = String(data.type || '')
  const title = String(data.title || '')
  const prompt = String(data.prompt || '')
  const mimeType = String(data.mime_type || '') as ImageArtifact['mime_type']
  const sizeBytes = Number(data.size_bytes)
  const sha256 = String(data.sha256 || '')
  const model = String(data.model || '')
  const createdAt = String(data.created_at || '')
  const expectedUrl = `/api/v1/artifacts/images/${id}`
  const expectedDownloadUrl = `${expectedUrl}?download=true`

  if (!UUID.test(id)
    || type !== 'image'
    || !title.trim()
    || !prompt.trim()
    || !IMAGE_MIME_TYPES.has(mimeType)
    || !Number.isSafeInteger(sizeBytes)
    || sizeBytes <= 0
    || !SHA256.test(sha256)
    || !model.trim()
    || !createdAt
    || Number.isNaN(Date.parse(createdAt))
    || data.url !== expectedUrl
    || data.download_url !== expectedDownloadUrl) {
    throw new Error('Image action does not contain a verified artifact contract')
  }

  return {
    id,
    type: 'image',
    title,
    prompt,
    mime_type: mimeType,
    size_bytes: sizeBytes,
    sha256,
    model,
    created_at: createdAt,
    url: expectedUrl,
    download_url: expectedDownloadUrl,
  }
}

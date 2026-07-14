import { getAuthToken, type ImageArtifact } from '@/lib/api'
import { sha256Hex } from '@/lib/sha256'

const IMAGE_MIME_TYPES = new Set<ImageArtifact['mime_type']>([
  'image/png',
  'image/jpeg',
  'image/webp',
])
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const SHA256 = /^[a-f0-9]{64}$/

export interface VerifiedImageArtifact extends ImageArtifact {
  /**
   * Runtime-only URL created from the bytes that passed MIME, size, digest and
   * raster decoding checks. It is deliberately omitted from persisted data.
   */
  object_url: string
}

interface VerifyImageArtifactOptions {
  fetchImpl?: typeof fetch
  signal?: AbortSignal
  digest?: (bytes: ArrayBuffer) => Promise<string>
  decode?: (blob: Blob) => Promise<void>
  createObjectURL?: (blob: Blob) => string
}

const IMAGE_INTENT = /(?:сгенерир(?:уй|уйте|овать|ованн|ую|уем)|нарису(?:й|йте)|созда(?:й|йте|ть)\s+(?:изображ|картин|иллюстр|фот)|\bgenerat(?:e|ed|ing)\b|\bdraw\b|\bcreate\s+(?:an?\s+)?(?:image|picture|illustration|photo)\b)/iu
const UNVERIFIED_IMAGE_SUCCESS = /(?:изображени[ея]|картинк[аи]|иллюстраци[яи])\s+(?:успешно\s+)?(?:создан[аоы]?|сгенерирован[аоы]?|готов[аоы]?)|(?:image|picture|illustration|photo)\s+(?:was\s+|is\s+)?(?:created|generated|ready)/iu

function hasRasterSignature(bytes: Uint8Array, mimeType: ImageArtifact['mime_type']): boolean {
  if (mimeType === 'image/png') {
    const signature = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]
    return bytes.length >= signature.length && signature.every((value, index) => bytes[index] === value)
  }
  if (mimeType === 'image/jpeg') {
    return bytes.length >= 4
      && bytes[0] === 0xff
      && bytes[1] === 0xd8
      && bytes.at(-2) === 0xff
      && bytes.at(-1) === 0xd9
  }
  return bytes.length >= 12
    && String.fromCharCode(...bytes.slice(0, 4)) === 'RIFF'
    && String.fromCharCode(...bytes.slice(8, 12)) === 'WEBP'
}

async function decodeRaster(blob: Blob): Promise<void> {
  if (typeof createImageBitmap === 'function') {
    const bitmap = await createImageBitmap(blob)
    if (bitmap.width <= 0 || bitmap.height <= 0) {
      bitmap.close()
      throw new Error('Decoded image has invalid dimensions')
    }
    bitmap.close()
    return
  }

  if (typeof Image === 'undefined' || typeof URL.createObjectURL !== 'function') {
    throw new Error('Raster decoding is unavailable')
  }
  const temporaryUrl = URL.createObjectURL(blob)
  try {
    await new Promise<void>((resolve, reject) => {
      const image = new Image()
      image.onload = () => image.naturalWidth > 0 && image.naturalHeight > 0
        ? resolve()
        : reject(new Error('Decoded image has invalid dimensions'))
      image.onerror = () => reject(new Error('Image bytes could not be decoded'))
      image.src = temporaryUrl
    })
  } finally {
    URL.revokeObjectURL(temporaryUrl)
  }
}

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

/**
 * Recognizes prompts whose success condition is a rendered image rather than
 * provider prose. The exact public flow "сгенерируй цветы" is intentionally
 * covered even though it does not contain the word "изображение".
 */
export function expectsImageArtifact(prompt: string): boolean {
  return IMAGE_INTENT.test(prompt.trim())
}

/** Provider success prose stays hidden until the client has verified bytes. */
export function safeContentBeforeImageVerification(content: string, imageExpected: boolean): string {
  if (imageExpected || UNVERIFIED_IMAGE_SUCCESS.test(content)) return ''
  return content
}

/**
 * Fetches the canonical same-origin artifact and fails closed unless the
 * response is the exact attested raster. The card receives an object URL made
 * from those verified bytes, so preview/open/download never depend on prose or
 * an unchecked second request.
 */
export async function verifyImageArtifact(
  value: Record<string, unknown> | ImageArtifact,
  options: VerifyImageArtifactOptions = {},
): Promise<VerifiedImageArtifact> {
  const artifact = normalizeImageArtifact(value as Record<string, unknown>)
  const token = getAuthToken()
  const headers: Record<string, string> = { Accept: artifact.mime_type }
  if (token) headers.Authorization = `Bearer ${token}`
  const response = await (options.fetchImpl ?? fetch)(artifact.url, {
    method: 'GET',
    headers,
    credentials: 'include',
    cache: 'no-store',
    signal: options.signal,
  })
  if (!response.ok) throw new Error(`Image bytes returned HTTP ${response.status}`)

  const contentType = response.headers.get('content-type')?.split(';', 1)[0]?.trim().toLowerCase()
  if (contentType !== artifact.mime_type) throw new Error('Image bytes returned an unexpected MIME type')

  const bytes = await response.arrayBuffer()
  if (bytes.byteLength !== artifact.size_bytes) throw new Error('Image byte length does not match the verified artifact')
  if (!hasRasterSignature(new Uint8Array(bytes), artifact.mime_type)) throw new Error('Image bytes do not match the declared raster format')
  const digest = await (options.digest ?? sha256Hex)(bytes)
  if (digest.toLowerCase() !== artifact.sha256) throw new Error('Image byte digest does not match the verified artifact')

  const blob = new Blob([bytes], { type: artifact.mime_type })
  await (options.decode ?? decodeRaster)(blob)
  const createObjectURL = options.createObjectURL ?? URL.createObjectURL.bind(URL)
  const objectUrl = createObjectURL(blob)
  if (!objectUrl) throw new Error('Verified image URL could not be created')
  return { ...artifact, object_url: objectUrl }
}

export function isVerifiedImageArtifact(value: ImageArtifact | VerifiedImageArtifact): value is VerifiedImageArtifact {
  return typeof (value as Partial<VerifiedImageArtifact>).object_url === 'string'
    && Boolean((value as Partial<VerifiedImageArtifact>).object_url?.trim())
}

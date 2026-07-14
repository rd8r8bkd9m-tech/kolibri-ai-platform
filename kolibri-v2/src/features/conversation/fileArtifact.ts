import { getAuthToken, type FileArtifact } from '@/lib/api'
import { sha256Hex } from '@/lib/sha256'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const SHA256 = /^[a-f0-9]{64}$/

const ARTIFACT_MIME: Record<FileArtifact['type'], string> = {
  'document.pdf': 'application/pdf',
  'document.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'document.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'document.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'site.bundle': 'application/zip',
  'app.bundle': 'application/zip',
}

export interface VerifiedFileArtifact extends FileArtifact {
  /** Runtime-only URL backed by the exact bytes verified in this browser. */
  object_url: string
  preview_url?: string
}

interface VerifyFileArtifactOptions {
  fetchImpl?: typeof fetch
  signal?: AbortSignal
  digest?: (bytes: ArrayBuffer) => Promise<string>
  createObjectURL?: (blob: Blob) => string
}

function string(value: unknown, maximum = 500): string {
  return typeof value === 'string' && value.trim() && value.length <= maximum ? value : ''
}

function hasFileSignature(bytes: Uint8Array, artifact: FileArtifact): boolean {
  if (artifact.type === 'document.pdf') {
    return bytes.length >= 8 && String.fromCharCode(...bytes.slice(0, 5)) === '%PDF-'
  }
  return bytes.length >= 4
    && bytes[0] === 0x50
    && bytes[1] === 0x4b
    && bytes[2] === 0x03
    && bytes[3] === 0x04
}

function signedPreviewUrl(value: unknown, artifactId: string): string {
  if (typeof value !== 'string' || value.length > 2400 || !value.startsWith('/api/v1/previews/')) {
    throw new Error('Project preview URL is unavailable')
  }
  const segments = value.split('/')
  const token = segments[6] ?? ''
  if (segments.length !== 8
    || segments[4] !== artifactId
    || segments[5] !== 's'
    || segments[7] !== 'index.html'
    || !/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(token)) {
    throw new Error('Project preview URL is invalid')
  }
  return value
}

/** Accept only the immutable CAS contract emitted by the backend artifact store. */
export function normalizeFileArtifact(data: Record<string, unknown>): FileArtifact {
  const id = string(data.id, 64)
  const type = string(data.type, 40) as FileArtifact['type']
  const revision = Number(data.revision)
  const title = string(data.title, 240)
  const filename = string(data.filename, 240)
  const mimeType = string(data.mime_type, 160)
  const sizeBytes = Number(data.size_bytes)
  const digest = string(data.sha256, 64)
  const createdAt = string(data.created_at, 64)
  const updatedAt = string(data.updated_at, 64)
  const metadata = data.metadata && typeof data.metadata === 'object' && !Array.isArray(data.metadata)
    ? data.metadata as Record<string, unknown>
    : null
  const canonical = `/api/v1/artifacts/${id}`
  const revisionUrl = `${canonical}?revision=${revision}`

  if (!UUID.test(id)
    || !(type in ARTIFACT_MIME)
    || !Number.isSafeInteger(revision)
    || revision <= 0
    || !title
    || !filename
    || mimeType !== ARTIFACT_MIME[type]
    || !Number.isSafeInteger(sizeBytes)
    || sizeBytes <= 0
    || !SHA256.test(digest)
    || !createdAt
    || Number.isNaN(Date.parse(createdAt))
    || !updatedAt
    || Number.isNaN(Date.parse(updatedAt))
    || !metadata
    || data.url !== canonical
    || data.download_url !== `${canonical}?download=true`
    || data.revision_url !== revisionUrl
    || data.revision_download_url !== `${revisionUrl}&download=true`
    || data.reopen_url !== `${canonical}/reopen`
    || data.history_url !== `${canonical}/history`) {
    throw new Error('File action does not contain a verified artifact contract')
  }

  return {
    id,
    type,
    revision,
    title,
    filename,
    mime_type: mimeType,
    size_bytes: sizeBytes,
    sha256: digest,
    created_at: createdAt,
    updated_at: updatedAt,
    metadata,
    url: canonical,
    download_url: `${canonical}?download=true`,
    revision_url: revisionUrl,
    revision_download_url: `${revisionUrl}&download=true`,
    reopen_url: `${canonical}/reopen`,
    history_url: `${canonical}/history`,
  }
}

/**
 * Re-fetch and hash immutable revision bytes before exposing open/download.
 * A provider message or an artifact-shaped JSON object can never create a card.
 */
export async function verifyFileArtifact(
  value: Record<string, unknown> | FileArtifact,
  options: VerifyFileArtifactOptions = {},
): Promise<VerifiedFileArtifact> {
  const artifact = normalizeFileArtifact(value as Record<string, unknown>)
  const token = getAuthToken()
  const headers: Record<string, string> = { Accept: artifact.mime_type }
  if (token) headers.Authorization = `Bearer ${token}`
  const response = await (options.fetchImpl ?? fetch)(artifact.revision_url, {
    method: 'GET',
    headers,
    credentials: 'include',
    cache: 'no-store',
    signal: options.signal,
  })
  if (!response.ok) throw new Error(`Artifact bytes returned HTTP ${response.status}`)
  const contentType = response.headers.get('content-type')?.split(';', 1)[0]?.trim().toLowerCase()
  if (contentType !== artifact.mime_type) throw new Error('Artifact bytes returned an unexpected MIME type')
  const bytes = await response.arrayBuffer()
  if (bytes.byteLength !== artifact.size_bytes) throw new Error('Artifact byte length does not match the manifest')
  if (!hasFileSignature(new Uint8Array(bytes), artifact)) throw new Error('Artifact bytes do not match the declared file format')
  const digest = await (options.digest ?? sha256Hex)(bytes)
  if (digest.toLowerCase() !== artifact.sha256) throw new Error('Artifact byte digest does not match the manifest')
  const blob = new Blob([bytes], { type: artifact.mime_type })
  const objectUrl = (options.createObjectURL ?? URL.createObjectURL.bind(URL))(blob)
  if (!objectUrl) throw new Error('Verified artifact URL could not be created')

  let previewUrl: string | undefined
  if (artifact.type === 'site.bundle' || artifact.type === 'app.bundle') {
    // A project preview is a short-lived, scope-bound capability. Never
    // reconstruct or persist it in the browser: reopen issues a fresh URL on
    // every history load and the signed path is inherited by relative assets.
    const reopen = await (options.fetchImpl ?? fetch)(artifact.reopen_url, {
      method: 'GET',
      headers: token ? { Authorization: `Bearer ${token}`, Accept: 'application/json' } : { Accept: 'application/json' },
      credentials: 'include',
      cache: 'no-store',
      signal: options.signal,
    })
    if (!reopen.ok) throw new Error(`Project preview returned HTTP ${reopen.status}`)
    const reopened = await reopen.json() as Record<string, unknown>
    const integrity = reopened.integrity && typeof reopened.integrity === 'object' && !Array.isArray(reopened.integrity)
      ? reopened.integrity as Record<string, unknown>
      : null
    if (Number(reopened.revision) !== artifact.revision || integrity?.digest !== artifact.sha256) {
      throw new Error('Project preview is not bound to the verified artifact revision')
    }
    previewUrl = signedPreviewUrl(reopened.preview_url, artifact.id)
  }
  return { ...artifact, object_url: objectUrl, ...(previewUrl ? { preview_url: previewUrl } : {}) }
}

export function isVerifiedFileArtifact(value: FileArtifact | VerifiedFileArtifact): value is VerifiedFileArtifact {
  return typeof (value as Partial<VerifiedFileArtifact>).object_url === 'string'
    && Boolean((value as Partial<VerifiedFileArtifact>).object_url?.trim())
}

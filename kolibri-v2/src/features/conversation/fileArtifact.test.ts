import { createHash } from 'node:crypto'
import { describe, expect, it, vi } from 'vitest'
import { normalizeFileArtifact, verifyFileArtifact } from './fileArtifact'

const id = '33333333-3333-4333-8333-333333333333'
const pdfBytes = new TextEncoder().encode('%PDF-1.7\nKolibri\n%%EOF')
const zipBytes = new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0x00, 0x00])
const artifact = {
  id,
  type: 'document.pdf',
  revision: 1,
  title: 'Отчёт',
  filename: 'report.pdf',
  mime_type: 'application/pdf',
  size_bytes: pdfBytes.byteLength,
  sha256: createHash('sha256').update(pdfBytes).digest('hex'),
  created_at: '2026-07-14T10:00:00Z',
  updated_at: '2026-07-14T10:00:01Z',
  metadata: { producer_capability: 'document.pdf' },
  url: `/api/v1/artifacts/${id}`,
  download_url: `/api/v1/artifacts/${id}?download=true`,
  revision_url: `/api/v1/artifacts/${id}?revision=1`,
  revision_download_url: `/api/v1/artifacts/${id}?revision=1&download=true`,
  reopen_url: `/api/v1/artifacts/${id}/reopen`,
  history_url: `/api/v1/artifacts/${id}/history`,
}

describe('verified file artifact boundary', () => {
  it('accepts only the canonical immutable artifact manifest', () => {
    expect(normalizeFileArtifact(artifact)).toEqual(artifact)
    expect(() => normalizeFileArtifact({ ...artifact, url: 'https://attacker.invalid/report.pdf' }))
      .toThrow('verified artifact contract')
    expect(() => normalizeFileArtifact({ ...artifact, mime_type: 'text/html' }))
      .toThrow('verified artifact contract')
  })

  it('creates an open/download URL only after bytes, MIME, signature and digest match', async () => {
    const createObjectURL = vi.fn().mockReturnValue('blob:verified-pdf')
    const fetchImpl = vi.fn().mockResolvedValue(new Response(pdfBytes, {
      status: 200,
      headers: { 'Content-Type': 'application/pdf' },
    }))

    await expect(verifyFileArtifact(artifact, { fetchImpl, createObjectURL })).resolves.toEqual({
      ...artifact,
      object_url: 'blob:verified-pdf',
    })
    expect(fetchImpl).toHaveBeenCalledWith(artifact.revision_url, expect.objectContaining({
      method: 'GET',
      credentials: 'include',
      cache: 'no-store',
    }))
  })

  it('never exposes corrupted bytes', async () => {
    const createObjectURL = vi.fn().mockReturnValue('blob:must-not-exist')
    await expect(verifyFileArtifact(artifact, {
      fetchImpl: vi.fn().mockResolvedValue(new Response(new Uint8Array(pdfBytes.byteLength), {
        headers: { 'Content-Type': 'application/pdf' },
      })),
      createObjectURL,
    })).rejects.toThrow()
    expect(createObjectURL).not.toHaveBeenCalled()
  })

  it('anchors project preview resources inside the artifact namespace', async () => {
    const previewUrl = `/api/v1/previews/${id}/s/eyJ0ZXN0Ijp0cnVlfQ.signature/index.html`
    const projectArtifact = {
      ...artifact,
      type: 'app.bundle',
      filename: 'app.zip',
      mime_type: 'application/zip',
      size_bytes: zipBytes.byteLength,
      sha256: createHash('sha256').update(zipBytes).digest('hex'),
      metadata: { producer_capability: 'app.create', entrypoint: 'index.html' },
    }

    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(new Response(zipBytes, {
        status: 200,
        headers: { 'Content-Type': 'application/zip' },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        artifact: projectArtifact,
        revision: 1,
        integrity: { algorithm: 'sha256', digest: projectArtifact.sha256 },
        preview_url: previewUrl,
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))

    await expect(verifyFileArtifact(projectArtifact, {
      fetchImpl,
      createObjectURL: vi.fn().mockReturnValue('blob:verified-app'),
    })).resolves.toMatchObject({
      object_url: 'blob:verified-app',
      preview_url: previewUrl,
    })
    expect(fetchImpl).toHaveBeenNthCalledWith(2, projectArtifact.reopen_url, expect.objectContaining({
      credentials: 'include',
      cache: 'no-store',
    }))
  })
})
